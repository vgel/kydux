import { parseArgs } from "util";
import * as crypto from "node:crypto";

const { values: args } = parseArgs({
  args: Bun.argv,
  options: {
    n_context: {
      type: "string",
      default: "128",
    },
    log: {
      type: "boolean",
      default: false,
    },
    mock_model: {
      type: "boolean",
      default: false,
    },
    python: {
      type: "string",
      default: "python",
    },
  },
  strict: false,
  allowPositionals: true,
});

const n_context = parseInt(args.n_context!.toString());
if (!n_context) {
  throw new Error("n_context must be an integer!");
}

const secret_url = `/${crypto.randomBytes(32).toString("hex")}`;

const server = Bun.serve({
  async fetch(req, server) {
    const url = new URL(req.url);
    console.log(req.method, url.pathname);

    if (url.pathname === "/")
      return new Response(
        await Bun.file("./server_interface.html")
          .text()
          .then((data) => {
            console.log(data);
            return data.replace("$$REPLACEME_CONTEXT_SIZE", n_context.toString());
          }),
        {
          headers: {
            "Content-Type": "text/html",
          },
        }
      );

    if (url.pathname === "/ws") {
      if (server.upgrade(req)) {
        return;
      }
      return new Response("Websocket upgrade failed", { status: 400 });
    }

    if (req.method === "POST" && url.pathname == secret_url) {
      const token = await req.text();
      server.publish("tokens", token);
      return new Response();
    }

    return new Response("404 not found", { status: 404 });
  },
  websocket: {
    open(ws) {
      ws.subscribe("tokens");
    },
    message(ws, message) {},
    close(ws) {
      ws.unsubscribe("tokens");
    },
  },
});

let worker = null;
if (args.python) {
  worker = Bun.spawn([args.python.toString(), `${__dirname}/worker.py`], {
    cwd: __dirname,
    env: {
      ...process.env,
      N_CONTEXT: n_context.toString(),
      LOG: args.log ? "1" : "",
      MOCK_MODEL: args.mock_model ? "1" : "",
      SECRET_URL: `http://localhost:${server.port}${secret_url}`,
    },
    onExit: () => {
      server.stop(true);
    },
  });
} else {
  console.log("not spawning worker: no --python");
}

console.log(`secret url: ${secret_url}`);
console.log(`server listening on ws://${server.hostname}:${server.port}`);
