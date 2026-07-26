import http from "node:http";

import { createApplication, loadRuntimeConfig } from "./src/application.mjs";

const config = await loadRuntimeConfig();
const application = await createApplication({ config });
const port = Number.parseInt(process.env.PORT || String(config.port || 3000), 10);

const server = http.createServer(application.handle);
server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`1BT Opportunity Radar listening on port ${port}\n`);
});

function shutdown(signal) {
  process.stdout.write(`Received ${signal}; closing server.\n`);
  server.close(() => process.exit(0));
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
