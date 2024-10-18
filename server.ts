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
    print_command: {
      type: "boolean",
      default: false,
    },
    secret_url_file: {
      type: "string",
      default: "",
    },
  },
  strict: false,
  allowPositionals: true,
});

const n_context = parseInt(args.n_context!.toString());
if (!n_context) {
  throw new Error("n_context must be an integer!");
}

let secret_url: string;
if (args.secret_url_file) {
  const secret_url_file: string = args.secret_url_file.toString();
  secret_url = (await Bun.file(secret_url_file).text()).trim();
} else {
  secret_url = `/${crypto.randomBytes(32).toString("hex")}`;
}

const server = Bun.serve({
  async fetch(req, server) {
    const url = new URL(req.url);

    if (url.pathname === "/")
      return new Response(
        await Bun.file("./server_interface.html")
          .text()
          .then((data) => {
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

if (args.python) {
  const env = {
    N_CONTEXT: n_context.toString(),
    LOG: args.log ? "1" : "",
    MOCK_MODEL: args.mock_model ? "1" : "",
    SECRET_URL: `http://localhost:${server.port}${secret_url}`,
  };
  if (args.print_command) {
    const envstr = Object.entries(env)
      .map(([k, v]) => `${k}=${v}`)
      .join(" ");
    console.log(`\n${envstr} ${args.python} worker.py\n`);
  } else {
    Bun.spawn([args.python.toString(), `${__dirname}/worker.py`], {
      cwd: __dirname,
      env: {
        ...process.env,
        ...env,
      },
      onExit: () => {
        server.stop(true);
      },
    });
  }
} else {
  console.log("not spawning worker: no --python");
}

console.log(`secret url: ${secret_url}`);
console.log(`server listening on ws://${server.hostname}:${server.port}`);
