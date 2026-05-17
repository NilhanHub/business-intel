"""Measure bounded uk_ie_d365_leads Google-grounded search round cost.

This utility intentionally mirrors the existing direct google-genai Google
Search grounding provider without changing lead-discovery behavior.

Official pricing constants below were checked against Google Cloud pricing:
https://cloud.google.com/vertex-ai/generative-ai/pricing

For Gemini 2.5 Flash standard online requests:
- Input text/image/video: $0.30 per 1M tokens.
- Text output, including response and reasoning: $2.50 per 1M tokens.
- Google Search grounding: 1,500 grounded prompts/day at no additional charge
  for Gemini 2.0 Flash, 2.5 Flash, and 2.5 Flash-Lite combined; then $35 per
  1,000 grounded prompts. A grounded prompt is charged once even if it creates
  multiple Google Search queries.

For Gemini 3 grounding:
- Google Search/Web Grounding includes 5,000 search queries/month aggregated
  across Gemini 3 models; then $14 per 1,000 search queries. Billing is per
  generated search query, not per prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from uk_ie_d365_leads.tools.lead_tools import (  # noqa: E402
    GOOGLE_GROUNDING_PROVIDER_PATH,
    SearchResult,
    _grounding_metadata_results,
    _prepare_google_native_env,
    build_query_plan,
    discover_d365_search_providers,
    effective_google_model,
    extract_d365_leads,
    google_native_readiness,
    normalize_public_url,
    parse_search_results,
    source_url_type,
)


EVIDENCE_DIR = PROJECT_ROOT / "Evidence"
DEFAULT_JSON_PATH = EVIDENCE_DIR / "UK_IE_D365_COST_MEASUREMENT.json"
DEFAULT_MD_PATH = EVIDENCE_DIR / "UK_IE_D365_COST_MEASUREMENT.md"

PRICING_SOURCE_URL = "https://cloud.google.com/vertex-ai/generative-ai/pricing"
MODEL_SOURCE_URL = "https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash"
GENAI_CLIENT_SOURCE_URL = "https://github.com/googleapis/python-genai/blob/main/README.md"

GEMINI_2_5_FLASH_INPUT_PER_1M_USD = 0.30
GEMINI_2_5_FLASH_OUTPUT_PER_1M_USD = 2.50
GEMINI_2_5_FLASH_GROUNDING_FREE_DAILY_PROMPTS = 1500
GEMINI_2_5_FLASH_GROUNDING_PER_1000_USD = 35.00

GEMINI_3_GROUNDING_FREE_MONTHLY_SEARCH_QUERIES = 5000
GEMINI_3_GROUNDING_PER_1000_SEARCH_QUERIES_USD = 14.00

MAX_TOTAL_REQUESTS = 80


@dataclass(frozen=True)
class RoundSpec:
    label: str
    request_count: int


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def plain(value: Any) -> Any:
    """Convert google-genai objects into JSON-safe data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    for method_name in ("model_dump", "to_json_dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                if method_name == "model_dump":
                    return plain(method(mode="json", exclude_none=True))
                return plain(method())
            except TypeError:
                try:
                    return plain(method())
                except Exception:  # noqa: BLE001 - best-effort serialization.
                    pass
            except Exception:  # noqa: BLE001 - best-effort serialization.
                pass
    if hasattr(value, "__dict__"):
        data = {
            key: val
            for key, val in vars(value).items()
            if not key.startswith("_") and not callable(val)
        }
        return plain(data)
    return str(value)


def get_nested(data: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        if isinstance(data, dict) and name in data:
            return data[name]
        if hasattr(data, name):
            return getattr(data, name)
    return None


def int_metric(data: Any, *names: str) -> int:
    value = get_nested(data, tuple(names))
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def env_snapshot() -> dict[str, Any]:
    return {
        "GOOGLE_GENAI_USE_VERTEXAI": os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"),
        "GOOGLE_CLOUD_PROJECT": os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "GOOGLE_CLOUD_LOCATION": os.environ.get("GOOGLE_CLOUD_LOCATION"),
        "D365_GOOGLE_MODEL": os.environ.get("D365_GOOGLE_MODEL"),
        "GEMINI_API_KEY_present": bool(os.environ.get("GEMINI_API_KEY")),
        "GOOGLE_API_KEY_present": bool(os.environ.get("GOOGLE_API_KEY")),
    }


def make_client() -> tuple[Any, dict[str, Any]]:
    from google import genai

    env_before_prepare = env_snapshot()
    _prepare_google_native_env()
    env_after_prepare = env_snapshot()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key), {
            "client_mode": "Gemini Developer API",
            "client_constructor": "genai.Client(api_key=...)",
            "auth_mode": "API_KEY",
            "project": None,
            "location": os.environ.get("GOOGLE_CLOUD_LOCATION") or "global",
            "env_before_prepare": env_before_prepare,
            "env_after_prepare": env_after_prepare,
        }

    readiness = google_native_readiness()
    project = readiness["adc"].get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
    return genai.Client(vertexai=True, project=project, location=location), {
        "client_mode": "Vertex AI",
        "client_constructor": "genai.Client(vertexai=True, project=project, location=location)",
        "auth_mode": "ADC",
        "project": project,
        "location": location,
        "env_before_prepare": env_before_prepare,
        "env_after_prepare": env_after_prepare,
    }


def grounded_prompt(query: str, limit: int) -> str:
    return (
        "Search the public web for the query below. Return JSON only: "
        '[{"title":"...","url":"https://...","snippet":"..."}]. '
        f"Return at most {max(1, min(int(limit or 5), 10))} results. "
        "Only include public web evidence for UK/Ireland Microsoft Dynamics 365 lead intelligence. "
        "Do not invent companies, URLs, or snippets.\n\n"
        f"Query: {query}"
    )


def merged_results(response: Any, *, source: str, limit: int, query: str, group: str) -> list[SearchResult]:
    text_results = parse_search_results(getattr(response, "text", "") or "", source=source, limit=limit)
    metadata_results = _grounding_metadata_results(response, source=source, limit=limit)
    merged: list[SearchResult] = []
    seen: set[str] = set()
    for result in text_results + metadata_results:
        normalized = normalize_public_url(result.url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(
            SearchResult(
                title=result.title,
                url=normalized,
                snippet=result.snippet,
                source=result.source,
                published_date=result.published_date,
                signal_class=group,
                source_url_type=source_url_type(normalized),
                source_query=query,
                source_query_group=group,
            )
        )
        if len(merged) >= limit:
            break
    return merged


def grounding_summary(response: Any) -> dict[str, Any]:
    search_queries: list[Any] = []
    support_urls: list[Any] = []
    chunk_urls: list[Any] = []
    grounding_chunks_count = 0
    grounding_supports_count = 0

    for candidate in getattr(response, "candidates", None) or []:
        metadata = (
            getattr(candidate, "grounding_metadata", None)
            or getattr(candidate, "groundingMetadata", None)
        )
        metadata_plain = plain(metadata) or {}
        if not isinstance(metadata_plain, dict):
            metadata_plain = {}

        queries = (
            metadata_plain.get("web_search_queries")
            or metadata_plain.get("webSearchQueries")
            or []
        )
        if isinstance(queries, list):
            search_queries.extend(queries)
        elif queries:
            search_queries.append(queries)

        chunks = (
            metadata_plain.get("grounding_chunks")
            or metadata_plain.get("groundingChunks")
            or []
        )
        if isinstance(chunks, list):
            grounding_chunks_count += len(chunks)
            for chunk in chunks:
                web = chunk.get("web") if isinstance(chunk, dict) else None
                if isinstance(web, dict):
                    chunk_urls.append(web.get("uri") or web.get("url"))

        supports = (
            metadata_plain.get("grounding_supports")
            or metadata_plain.get("groundingSupports")
            or []
        )
        if isinstance(supports, list):
            grounding_supports_count += len(supports)
            for support in supports:
                if not isinstance(support, dict):
                    continue
                for chunk in support.get("grounding_chunk_indices", []) or support.get("groundingChunkIndices", []) or []:
                    if isinstance(chunks, list) and isinstance(chunk, int) and 0 <= chunk < len(chunks):
                        web = chunks[chunk].get("web") if isinstance(chunks[chunk], dict) else None
                        if isinstance(web, dict):
                            support_urls.append(web.get("uri") or web.get("url"))

    queries_out = unique_strings(search_queries)
    chunk_urls_out = unique_strings(chunk_urls)
    support_urls_out = unique_strings(support_urls)
    return {
        "web_search_queries": queries_out,
        "web_search_query_count": len(queries_out),
        "grounding_chunks_count": grounding_chunks_count,
        "grounding_supports_count": grounding_supports_count,
        "grounding_chunk_urls_count": len(chunk_urls_out),
        "grounding_support_urls_count": len(support_urls_out),
        "has_web_grounding_result": bool(queries_out or chunk_urls_out or support_urls_out),
    }


def usage_summary(response: Any) -> dict[str, Any]:
    usage = plain(getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)) or {}
    prompt_tokens = int_metric(usage, "prompt_token_count", "promptTokenCount")
    candidates_tokens = int_metric(usage, "candidates_token_count", "candidatesTokenCount")
    thoughts_tokens = int_metric(usage, "thoughts_token_count", "thoughtsTokenCount")
    total_tokens = int_metric(usage, "total_token_count", "totalTokenCount")
    cached_tokens = int_metric(usage, "cached_content_token_count", "cachedContentTokenCount")
    tool_tokens = int_metric(usage, "tool_use_prompt_token_count", "toolUsePromptTokenCount")
    output_tokens_for_cost = candidates_tokens
    if thoughts_tokens and total_tokens >= prompt_tokens + candidates_tokens + thoughts_tokens:
        output_tokens_for_cost += thoughts_tokens
    return {
        "raw_usage_metadata": usage,
        "prompt_token_count": prompt_tokens,
        "candidates_token_count": candidates_tokens,
        "thoughts_token_count": thoughts_tokens,
        "total_token_count": total_tokens,
        "cached_content_token_count": cached_tokens,
        "tool_use_prompt_token_count": tool_tokens,
        "input_tokens_for_cost": prompt_tokens + tool_tokens,
        "output_tokens_for_cost": output_tokens_for_cost,
    }


def model_version(response: Any) -> str | None:
    value = getattr(response, "model_version", None) or getattr(response, "modelVersion", None)
    return str(value) if value else None


def run_grounded_request(
    *,
    client: Any,
    model: str,
    query: str,
    group: str,
    max_results: int,
) -> tuple[dict[str, Any], list[SearchResult]]:
    from google.genai import types

    started = now_utc()
    try:
        response = client.models.generate_content(
            model=model,
            contents=grounded_prompt(query, max_results),
            config=types.GenerateContentConfig(
                tools=[types.Tool(googleSearch=types.GoogleSearch())],
                temperature=0,
                maxOutputTokens=2048,
            ),
        )
        results = merged_results(
            response,
            source="google_grounding",
            limit=max_results,
            query=query,
            group=group,
        )
        finished = now_utc()
        usage = usage_summary(response)
        grounding = grounding_summary(response)
        return {
            "query": query,
            "query_group": group,
            "started_at": started,
            "finished_at": finished,
            "status": "ok",
            "result_count": len(results),
            "usage_metadata": usage,
            "grounding_metadata": grounding,
            "model_version": model_version(response),
            "error": None,
        }, results
    except Exception as exc:  # noqa: BLE001 - bounded meter should persist failure details.
        finished = now_utc()
        return {
            "query": query,
            "query_group": group,
            "started_at": started,
            "finished_at": finished,
            "status": "error",
            "result_count": 0,
            "usage_metadata": {},
            "grounding_metadata": {},
            "model_version": None,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }, []


def planned_queries(request_count: int) -> list[dict[str, str]]:
    plan = build_query_plan()
    if not plan:
        raise RuntimeError("build_query_plan returned no live-search queries")
    selected: list[dict[str, str]] = []
    while len(selected) < request_count:
        selected.extend(plan)
    return selected[:request_count]


def sum_usage(requests: list[dict[str, Any]]) -> dict[str, int]:
    fields = [
        "prompt_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "total_token_count",
        "cached_content_token_count",
        "tool_use_prompt_token_count",
        "input_tokens_for_cost",
        "output_tokens_for_cost",
    ]
    return {
        field: sum(int(req.get("usage_metadata", {}).get(field) or 0) for req in requests)
        for field in fields
    }


def sum_grounding(requests: list[dict[str, Any]]) -> dict[str, int]:
    billable_prompt_estimate = 0
    search_query_count = 0
    grounding_chunks_count = 0
    grounding_supports_count = 0
    for req in requests:
        grounding = req.get("grounding_metadata", {}) or {}
        search_query_count += int(grounding.get("web_search_query_count") or 0)
        grounding_chunks_count += int(grounding.get("grounding_chunks_count") or 0)
        grounding_supports_count += int(grounding.get("grounding_supports_count") or 0)
        if req.get("status") == "ok" and (
            grounding.get("has_web_grounding_result") or int(req.get("result_count") or 0) > 0
        ):
            billable_prompt_estimate += 1
    return {
        "web_search_query_count": search_query_count,
        "grounding_chunks_count": grounding_chunks_count,
        "grounding_supports_count": grounding_supports_count,
        "billable_grounded_prompt_count_estimate": billable_prompt_estimate,
    }


def estimate_cost(model: str, usage: dict[str, int], grounding: dict[str, int]) -> dict[str, Any]:
    lower_model = model.lower()
    input_cost = None
    output_cost = None
    grounding_normal = None
    grounding_worst = None
    notes: list[str] = []

    if lower_model.startswith("gemini-2.5-flash"):
        input_cost = usage["input_tokens_for_cost"] / 1_000_000 * GEMINI_2_5_FLASH_INPUT_PER_1M_USD
        output_cost = usage["output_tokens_for_cost"] / 1_000_000 * GEMINI_2_5_FLASH_OUTPUT_PER_1M_USD
        billable_prompts = grounding["billable_grounded_prompt_count_estimate"]
        grounding_normal = 0.0
        grounding_worst = billable_prompts / 1000 * GEMINI_2_5_FLASH_GROUNDING_PER_1000_USD
        notes.append(
            "Normal-case grounding assumes the billing account remains inside the 1,500 grounded prompts/day allowance."
        )
        notes.append("Worst-case grounding assumes the daily free allowance was already exhausted before this run.")
    elif lower_model.startswith("gemini-3"):
        input_cost = None
        output_cost = None
        search_queries = grounding["web_search_query_count"]
        grounding_normal = 0.0
        grounding_worst = search_queries / 1000 * GEMINI_3_GROUNDING_PER_1000_SEARCH_QUERIES_USD
        notes.append(
            "Gemini 3 grounding is priced per generated search query, with 5,000 search queries/month at no additional charge."
        )
        notes.append("Gemini 3 token prices are not hardcoded unless this utility is extended with a verified SKU mapping.")
    else:
        notes.append(f"No hardcoded token or grounding price exists for model {model}; cost is incomplete.")

    deterministic_local_classification_cost_usd = 0.0
    public_http_checks_cost_usd = 0.0
    normal_total = None
    worst_total = None
    if input_cost is not None and output_cost is not None and grounding_normal is not None and grounding_worst is not None:
        normal_total = input_cost + output_cost + grounding_normal + deterministic_local_classification_cost_usd
        worst_total = input_cost + output_cost + grounding_worst + deterministic_local_classification_cost_usd

    return {
        "input_token_estimated_cost_usd": input_cost,
        "output_token_estimated_cost_usd": output_cost,
        "grounding_estimated_cost_usd_normal_free_allowance": grounding_normal,
        "grounding_estimated_cost_usd_worst_case_free_allowance_exhausted": grounding_worst,
        "public_http_redirect_or_page_checks_cost_usd": public_http_checks_cost_usd,
        "deterministic_local_classification_cost_usd": deterministic_local_classification_cost_usd,
        "estimated_total_usd_normal_free_allowance": normal_total,
        "estimated_total_usd_worst_case_free_allowance_exhausted": worst_total,
        "notes": notes,
    }


def run_round(spec: RoundSpec, *, client: Any, model: str, max_results: int) -> dict[str, Any]:
    started = now_utc()
    requests: list[dict[str, Any]] = []
    raw_results: list[SearchResult] = []
    for item in planned_queries(spec.request_count):
        req, results = run_grounded_request(
            client=client,
            model=model,
            query=item["query"],
            group=item["signal_class"],
            max_results=max_results,
        )
        requests.append(req)
        raw_results.extend(results)
        if req["status"] == "error":
            break
    extraction = extract_d365_leads(
        raw_results,
        max_results=max(len(raw_results), 1),
        include_rejected=True,
    )
    usage = sum_usage(requests)
    grounding = sum_grounding(requests)
    costs = estimate_cost(model, usage, grounding)
    surfaced_count = len(extraction["surfaced_leads"])
    accepted_or_provisional = surfaced_count
    finished = now_utc()
    normal_total = costs.get("estimated_total_usd_normal_free_allowance")
    worst_total = costs.get("estimated_total_usd_worst_case_free_allowance_exhausted")
    return {
        "label": spec.label,
        "requested_live_grounded_requests": spec.request_count,
        "actual_live_grounded_requests": len(requests),
        "started_at": started,
        "finished_at": finished,
        "status": "ok" if all(req["status"] == "ok" for req in requests) else "error",
        "max_results_per_request": max_results,
        "query_plan_unique_count": len(build_query_plan()),
        "query_plan_reused_to_reach_target": spec.request_count > len(build_query_plan()),
        "request_summaries": requests,
        "usage_totals": usage,
        "grounding_totals": grounding,
        "result_count": len(raw_results),
        "lead_count": surfaced_count,
        "tier_counts": extraction["tier_counts"],
        "rejected_count": len(extraction["rejected_leads"]),
        "estimated_cost": costs,
        "estimated_cost_per_accepted_or_provisional_candidate_normal_usd": (
            normal_total / accepted_or_provisional if normal_total is not None and accepted_or_provisional else None
        ),
        "estimated_cost_per_accepted_or_provisional_candidate_worst_usd": (
            worst_total / accepted_or_provisional if worst_total is not None and accepted_or_provisional else None
        ),
    }


def money(value: Any) -> str:
    if value is None:
        return "unknown"
    return f"${float(value):.6f}"


def markdown_report(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# UK/IE D365 Cost Measurement")
    lines.append("")
    lines.append(f"- Generated at: `{data['generated_at']}`")
    lines.append(f"- Model: `{data['model']['effective_model_name']}`")
    lines.append(f"- Provider path: `{data['provider']['provider_path']}`")
    lines.append(f"- Provider client mode: `{data['provider']['client_mode']}`")
    lines.append(f"- Project present: `{data['provider']['project_present']}`")
    lines.append(f"- Location: `{data['provider']['location']}`")
    lines.append(f"- Billing data directly readable: `{data['billing_visibility']['actual_cost_data_directly_readable']}`")
    lines.append(f"- Billing lag prevents exact delta measurement: `{data['billing_visibility']['billing_lag_prevents_exact_delta']}`")
    lines.append("")
    surface = data["pricing_surface_determination"]
    lines.append("## Pricing Surface Determination")
    lines.append(f"- Detected provider mode: `{surface['detected_provider_mode']}`")
    lines.append(f"- Detected model: `{surface['detected_model']}`")
    lines.append(f"- Detected project: `{surface['detected_project']}`")
    lines.append(f"- Detected location: `{surface['detected_location']}`")
    lines.append(f"- Client initialization path: `{surface['client_initialization_path']}`")
    lines.append(f"- Requests billed under `business-intel-123`: `{surface['requests_billed_under_business_intel_123']}`")
    lines.append(f"- Pricing surface used: `{surface['pricing_surface_used']}`")
    lines.append(f"- Pricing page/source used: {surface['pricing_page_source_used']}")
    lines.append(f"- Remaining uncertainty: {surface['remaining_uncertainty']}")
    lines.append("")
    lines.append("Env vars checked:")
    for key, value in surface["env_vars_checked"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Pricing Assumptions")
    for item in data["pricing_assumptions"]["items"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Rounds")
    lines.append("| Round | Requests | Search queries | Input tokens for cost | Output tokens for cost | Normal estimate | Worst-case estimate | Leads | Tiers |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for round_data in data["rounds"]:
        usage = round_data["usage_totals"]
        grounding = round_data["grounding_totals"]
        costs = round_data["estimated_cost"]
        lines.append(
            "| {label} | {requests} | {queries} | {input_tokens} | {output_tokens} | {normal} | {worst} | {leads} | {tiers} |".format(
                label=round_data["label"],
                requests=round_data["actual_live_grounded_requests"],
                queries=grounding["web_search_query_count"],
                input_tokens=usage["input_tokens_for_cost"],
                output_tokens=usage["output_tokens_for_cost"],
                normal=money(costs["estimated_total_usd_normal_free_allowance"]),
                worst=money(costs["estimated_total_usd_worst_case_free_allowance_exhausted"]),
                leads=round_data["lead_count"],
                tiers=json.dumps(round_data["tier_counts"], sort_keys=True),
            )
        )
    lines.append("")
    lines.append("## Cost Notes")
    lines.append("- Normal-case estimate assumes the Google Search grounding free allowance applies.")
    lines.append("- Worst-case estimate assumes the free grounding allowance has already been exhausted.")
    lines.append("- Deterministic Python classification has expected zero API cost.")
    lines.append("- This utility did not perform public HTTP redirect/page checks.")
    lines.append("- Immediate project-level billing deltas were not available in local CLI/API checks.")
    lines.append("")
    lines.append("## Source URLs")
    lines.append(f"- Pricing: {PRICING_SOURCE_URL}")
    lines.append(f"- Model card: {MODEL_SOURCE_URL}")
    lines.append(f"- google-genai client mode docs: {GENAI_CLIENT_SOURCE_URL}")
    lines.append("")
    return "\n".join(lines)


def parse_round_specs(values: list[str]) -> list[RoundSpec]:
    specs: list[RoundSpec] = []
    for value in values:
        if "=" in value:
            label, count_text = value.split("=", 1)
        else:
            label = f"Round {chr(ord('A') + len(specs))}"
            count_text = value
        count = int(count_text)
        if count < 1:
            raise ValueError(f"Round request count must be positive: {value}")
        specs.append(RoundSpec(label=label.strip() or f"Round {len(specs) + 1}", request_count=count))
    return specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", dest="rounds", action="append", default=[], help="Round spec like A=20 or B=50")
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD_PATH)
    args = parser.parse_args()

    specs = parse_round_specs(args.rounds or ["A=20", "B=50"])
    total_requested = sum(spec.request_count for spec in specs)
    if total_requested > MAX_TOTAL_REQUESTS:
        raise SystemExit(f"Refusing to run {total_requested} requests; hard cap is {MAX_TOTAL_REQUESTS}.")

    model_name, model_source = effective_google_model()
    providers = discover_d365_search_providers()
    readiness = google_native_readiness()
    if providers.get("chosen_provider") != "google_grounding":
        raise SystemExit(f"Refusing to run: chosen provider is {providers.get('chosen_provider')!r}, not google_grounding.")
    if not readiness.get("ready"):
        raise SystemExit(f"Refusing to run: Google-native readiness is false: {readiness.get('reason')}")

    env_before_client = env_snapshot()
    client, client_info = make_client()
    project = client_info["project"]
    location = client_info["location"]
    started = now_utc()
    rounds = [run_round(spec, client=client, model=model_name, max_results=max(1, min(args.max_results, 10))) for spec in specs]
    finished = now_utc()

    data = {
        "generated_at": now_utc(),
        "started_at": started,
        "finished_at": finished,
        "argv": sys.argv,
        "model": {
            "effective_model_name": model_name,
            "model_source": model_source,
            "model_versions_returned": sorted(
                {
                    str(req.get("model_version"))
                    for round_data in rounds
                    for req in round_data["request_summaries"]
                    if req.get("model_version")
                }
            ),
        },
        "provider": {
            "provider": "google_grounding",
            "provider_path": GOOGLE_GROUNDING_PROVIDER_PATH,
            "client_mode": client_info["client_mode"],
            "client_constructor": client_info["client_constructor"],
            "auth_mode": client_info["auth_mode"],
            "project_present": bool(project),
            "project_id": project,
            "location": location,
            "env_before_client": env_before_client,
            "env_before_prepare": client_info["env_before_prepare"],
            "env_after_prepare": client_info["env_after_prepare"],
            "google_native_readiness": readiness,
        },
        "pricing_surface_determination": {
            "detected_provider_mode": client_info["client_mode"],
            "detected_model": model_name,
            "detected_project": project,
            "detected_location": location,
            "env_vars_checked": {
                "GOOGLE_GENAI_USE_VERTEXAI": client_info["env_after_prepare"]["GOOGLE_GENAI_USE_VERTEXAI"],
                "GOOGLE_CLOUD_PROJECT": client_info["env_after_prepare"]["GOOGLE_CLOUD_PROJECT"],
                "GOOGLE_CLOUD_LOCATION": client_info["env_after_prepare"]["GOOGLE_CLOUD_LOCATION"],
                "D365_GOOGLE_MODEL": client_info["env_after_prepare"]["D365_GOOGLE_MODEL"],
                "GEMINI_API_KEY_present": client_info["env_after_prepare"]["GEMINI_API_KEY_present"],
                "GOOGLE_API_KEY_present": client_info["env_after_prepare"]["GOOGLE_API_KEY_present"],
            },
            "client_initialization_path": client_info["client_constructor"],
            "lead_tools_client_path": (
                "uk_ie_d365_leads/tools/lead_tools.py uses genai.Client(api_key=...) when a Gemini API key is present; "
                "otherwise it prepares ADC env and calls genai.Client(vertexai=True, project=project, location=location)."
            ),
            "requests_billed_under_business_intel_123": bool(
                client_info["client_mode"] == "Vertex AI" and project == "business-intel-123"
            ),
            "pricing_surface_used": (
                "Vertex AI / Google Cloud generative AI pricing"
                if client_info["client_mode"] == "Vertex AI"
                else "Gemini Developer API pricing"
            ),
            "pricing_page_source_used": PRICING_SOURCE_URL,
            "gemini_enterprise_agent_platform_note": (
                "The Google Cloud pricing URL may redirect to a Gemini Enterprise Agent Platform pricing page, "
                "but this meter invokes google-genai models.generate_content through the Vertex AI client, "
                "not a deployed Gemini Enterprise agent."
            ),
            "remaining_uncertainty": (
                "Low for pricing surface if project billing linkage remains business-intel-123; "
                "actual immediate billed delta remains unavailable without billing export or delayed invoice data."
            ),
            "client_docs_source": GENAI_CLIENT_SOURCE_URL,
        },
        "billing_visibility": {
            "actual_cost_data_directly_readable": False,
            "billing_lag_prevents_exact_delta": True,
            "notes": [
                "gcloud billing projects describe can read billing linkage.",
                "Cloud Billing Catalog API can read pricing SKUs.",
                "No BigQuery billing export dataset was visible in business-intel-123 during preflight metadata checks.",
                "Cloud Billing Budgets API was disabled and was not enabled.",
                "Immediate billing deltas are not expected to be available from local CLI/API checks.",
            ],
        },
        "pricing_assumptions": {
            "source_urls": [PRICING_SOURCE_URL, MODEL_SOURCE_URL],
            "items": [
                "Gemini 2.5 Flash standard input tokens: $0.30 per 1M tokens.",
                "Gemini 2.5 Flash standard text output, including response and reasoning: $2.50 per 1M tokens.",
                "Gemini 2.5 Flash Google Search grounding: 1,500 grounded prompts/day at no additional charge, then $35 per 1,000 grounded prompts.",
                "Gemini 3 Google Search grounding: 5,000 search queries/month at no additional charge, then $14 per 1,000 search queries.",
                "Model usage fees apply separately from grounding fees.",
            ],
            "constants": {
                "gemini_2_5_flash_input_per_1m_usd": GEMINI_2_5_FLASH_INPUT_PER_1M_USD,
                "gemini_2_5_flash_output_per_1m_usd": GEMINI_2_5_FLASH_OUTPUT_PER_1M_USD,
                "gemini_2_5_flash_grounding_free_daily_prompts": GEMINI_2_5_FLASH_GROUNDING_FREE_DAILY_PROMPTS,
                "gemini_2_5_flash_grounding_per_1000_usd": GEMINI_2_5_FLASH_GROUNDING_PER_1000_USD,
                "gemini_3_grounding_free_monthly_search_queries": GEMINI_3_GROUNDING_FREE_MONTHLY_SEARCH_QUERIES,
                "gemini_3_grounding_per_1000_search_queries_usd": GEMINI_3_GROUNDING_PER_1000_SEARCH_QUERIES_USD,
            },
        },
        "rounds": rounds,
        "total_live_grounded_requests": sum(round_data["actual_live_grounded_requests"] for round_data in rounds),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    args.output_md.write_text(markdown_report(data), encoding="utf-8")
    print(json.dumps({
        "output_json": str(args.output_json),
        "output_md": str(args.output_md),
        "total_live_grounded_requests": data["total_live_grounded_requests"],
        "model": model_name,
        "rounds": [
            {
                "label": round_data["label"],
                "requests": round_data["actual_live_grounded_requests"],
                "normal_cost_usd": round_data["estimated_cost"]["estimated_total_usd_normal_free_allowance"],
                "worst_cost_usd": round_data["estimated_cost"]["estimated_total_usd_worst_case_free_allowance_exhausted"],
            }
            for round_data in rounds
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
