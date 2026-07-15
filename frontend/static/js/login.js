(function () {
  "use strict";

  const form = document.getElementById("loginForm");
  const usernameInput = document.getElementById("username");
  const passwordInput = document.getElementById("password");
  const errorElement = document.getElementById("loginError");
  const submitButton = document.getElementById("loginBtn");

  function setLoading(isLoading) {
    submitButton.classList.toggle("loading", isLoading);
    submitButton.disabled = isLoading;
    submitButton.setAttribute("aria-busy", String(isLoading));
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    errorElement.textContent = "";
    usernameInput.classList.remove("error");
    passwordInput.classList.remove("error");

    const username = usernameInput.value.trim();
    const password = passwordInput.value;
    if (!username) {
      errorElement.textContent = "Username is required";
      usernameInput.classList.add("error");
      usernameInput.focus();
      return;
    }
    if (!password) {
      errorElement.textContent = "Password is required";
      passwordInput.classList.add("error");
      passwordInput.focus();
      return;
    }

    setLoading(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username, password: password }),
      });
      let data = {};
      try {
        data = await response.json();
      } catch (_error) {
        data = {};
      }
      if (!response.ok || !data.ok) {
        let fallback = "Invalid username or password";
        if (response.status === 429) {
          fallback = "Too many sign-in attempts. Try again later.";
        } else if (response.status >= 500) {
          fallback = "Sign-in is temporarily unavailable.";
        }
        throw new Error(typeof data.detail === "string" ? data.detail : fallback);
      }
      location.assign("/app");
    } catch (error) {
      errorElement.textContent = error instanceof Error ? error.message : "Authentication failed";
      passwordInput.value = "";
      passwordInput.classList.add("error");
      passwordInput.focus();
    } finally {
      setLoading(false);
    }
  });
}());
