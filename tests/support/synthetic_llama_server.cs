// Synthetic transport fixture only: no inference, model reads, tools or egress.
// C# 5 / .NET Framework; every response is fixed and contains no request text.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

internal static class SyntheticLlamaServer
{
    private const int LifetimeSeconds = 120;
    private const int MaxRequests = 64;
    private const int MaxBody = 262144;
    private static readonly object Gate = new object();
    private static readonly List<TcpClient> Clients = new List<TcpClient>();
    private static readonly Stopwatch Lifetime = Stopwatch.StartNew();

    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--version")
        {
            Console.WriteLine("synthetic-llama-fixture.v1 (no inference)");
            return 0;
        }
        int port;
        try { if (!Arguments(args, out port)) return 2; }
        catch { return 2; }
        TcpListener listener = new TcpListener(IPAddress.Loopback, port);
        try
        {
            listener.Start(4);
            int accepted = 0;
            while (Lifetime.Elapsed.TotalSeconds < LifetimeSeconds && accepted < MaxRequests)
            {
                if (!listener.Pending()) { Thread.Sleep(20); continue; }
                TcpClient client = listener.AcceptTcpClient();
                accepted++;
                lock (Gate)
                {
                    if (Clients.Count >= 4) { client.Close(); continue; }
                    Clients.Add(client);
                }
                Thread worker = new Thread(delegate() { Handle(client, port); });
                worker.IsBackground = true;
                worker.Start();
            }
            return 0;
        }
        catch { return 3; }
        finally
        {
            listener.Stop();
            lock (Gate) { foreach (TcpClient client in Clients) client.Close(); }
        }
    }

    private static bool Arguments(string[] args, out int port)
    {
        port = 0;
        Dictionary<string, string> values = new Dictionary<string, string>();
        bool noWeb = false;
        for (int i = 0; i < args.Length; i++)
        {
            string key = args[i];
            if (key == "--no-webui") { if (noWeb) return false; noWeb = true; continue; }
            if (key != "-m" && key != "--host" && key != "--port" && key != "-ngl" && key != "-c") return false;
            if (++i >= args.Length || values.ContainsKey(key)) return false;
            values.Add(key, args[i]);
        }
        int context;
        string model, host, portText, layers, contextText;
        return noWeb && values.Count == 5
            && values.TryGetValue("-m", out model) && Path.IsPathRooted(model)
            && Path.GetFileName(model) == "synthetic-fixture.gguf"
            && values.TryGetValue("--host", out host) && host == "127.0.0.1"
            && values.TryGetValue("--port", out portText) && Int32.TryParse(portText, out port)
            && port >= 1024 && port <= 65535 && port != 8765 && port != 8766
            && values.TryGetValue("-ngl", out layers) && layers == "0"
            && values.TryGetValue("-c", out contextText) && Int32.TryParse(contextText, out context)
            && context >= 512 && context <= 8192;
    }

    private static void Handle(TcpClient client, int port)
    {
        try
        {
            client.ReceiveTimeout = 2000;
            client.SendTimeout = 2000;
            using (NetworkStream stream = client.GetStream())
            {
                string method, path;
                byte[] body;
                if (!ReadRequest(stream, port, out method, out path, out body)) { Json(stream, 400, "{\"error\":\"synthetic_request_refused\"}"); return; }
                if (method == "GET" && path == "/health") { Json(stream, 200, "{\"status\":\"ok\"}"); return; }
                if (method == "GET" && path == "/v1/models")
                {
                    Json(stream, 200, "{\"data\":[{\"id\":\"synthetic-fixture\",\"input_modalities\":[\"text\"]}]}"); return;
                }
                if (method != "POST" || (path != "/v1/chat/completions" && path != "/v1/chat/completions/input_tokens")) { Json(stream, 404, "{\"error\":\"synthetic_route_refused\"}"); return; }
                bool streaming;
                string scenario;
                try { scenario = Scenario(body, out streaming); }
                catch (ArgumentException) { scenario = null; streaming = false; }
                catch (InvalidOperationException) { scenario = null; streaming = false; }
                catch (InvalidCastException) { scenario = null; streaming = false; }
                if (scenario == null) { Json(stream, 400, "{\"error\":\"synthetic_scenario_refused\"}"); return; }
                if (path.EndsWith("/input_tokens", StringComparison.Ordinal))
                {
                    // A fixed synthetic counter receipt, not real tokenizer evidence.
                    Json(stream, 200, "{\"object\":\"response.input_tokens\",\"input_tokens\":32}"); return;
                }
                if (!streaming)
                {
                    Json(stream, 200, "{\"choices\":[{\"message\":{\"role\":\"assistant\",\"content\":\"Synthetic fixture answer.\"},\"finish_reason\":\"stop\"}]}"); return;
                }
                Write(stream, "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n");
                int pieces = scenario == "cancel" ? 160 : 3;
                for (int i = 0; i < pieces && Lifetime.Elapsed.TotalSeconds < LifetimeSeconds - 1; i++)
                {
                    Write(stream, "data: {\"choices\":[{\"index\":0,\"delta\":{\"content\":\"Synthetic chunk. \"},\"finish_reason\":null}]}\n\n");
                    Thread.Sleep(scenario == "cancel" ? 125 : 80);
                }
                Write(stream, "data: {\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n\n");
            }
        }
        catch { /* Fixed outcomes only; no exceptions or request data logged. */ }
        finally { client.Close(); lock (Gate) { Clients.Remove(client); } }
    }

    private static bool ReadRequest(NetworkStream stream, int port, out string method, out string path, out byte[] body)
    {
        method = path = null; body = null;
        List<byte> header = new List<byte>();
        while (header.Count < 16384)
        {
            if (Lifetime.Elapsed.TotalSeconds >= LifetimeSeconds) return false;
            int value = stream.ReadByte();
            if (value < 0 || value > 127 || value == 0) return false;
            header.Add((byte)value);
            int count = header.Count;
            if (count >= 4 && header[count - 4] == 13 && header[count - 3] == 10 && header[count - 2] == 13 && header[count - 1] == 10) break;
        }
        if (header.Count >= 16384) return false;
        string[] lines = Encoding.ASCII.GetString(header.ToArray()).Split(new string[] { "\r\n" }, StringSplitOptions.None);
        string[] request = lines[0].Split(' ');
        if (request.Length != 3 || request[2] != "HTTP/1.1") return false;
        method = request[0]; path = request[1];
        Dictionary<string, string> headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (int i = 1; i < lines.Length && lines[i].Length != 0; i++)
        {
            int colon = lines[i].IndexOf(':');
            if (colon <= 0) return false;
            string key = lines[i].Substring(0, colon);
            if (headers.ContainsKey(key)) return false;
            headers.Add(key, lines[i].Substring(colon + 1).Trim());
        }
        string host, lengthText;
        if (!headers.TryGetValue("Host", out host) || host != "127.0.0.1:" + port || headers.ContainsKey("Transfer-Encoding")) return false;
        int length = 0;
        if (headers.TryGetValue("Content-Length", out lengthText) && (!Int32.TryParse(lengthText, out length) || length < 0 || length > MaxBody)) return false;
        if (method == "POST" && length == 0) return false;
        body = new byte[length];
        int read = 0;
        while (read < length)
        {
            if (Lifetime.Elapsed.TotalSeconds >= LifetimeSeconds) return false;
            int count = stream.Read(body, read, length - read);
            if (count == 0) return false;
            read += count;
        }
        return true;
    }

    private static string Scenario(byte[] body, out bool streaming)
    {
        streaming = false;
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        serializer.MaxJsonLength = MaxBody;
        serializer.RecursionLimit = 24;
        Dictionary<string, object> request = serializer.DeserializeObject(new UTF8Encoding(false, true).GetString(body)) as Dictionary<string, object>;
        if (request == null) return null;
        object value;
        if (request.TryGetValue("stream", out value)) { if (!(value is bool)) return null; streaming = (bool)value; }
        if (!request.TryGetValue("messages", out value)) return null;
        object[] messages = value as object[];
        if (messages == null || messages.Length == 0 || messages.Length > 64) return null;
        string lastUser = null;
        foreach (object item in messages)
        {
            Dictionary<string, object> message = item as Dictionary<string, object>;
            object role, content;
            if (message == null || !message.TryGetValue("role", out role) || !(role is string) || !message.TryGetValue("content", out content) || !(content is string)) return null;
            if ((string)role == "user") lastUser = (string)content;
        }
        switch (lastUser)
        {
            case "Reply with OK. This is a synthetic local capability probe.": return "probe";
            case "Synthetic streaming acceptance.": return "stream";
            case "Synthetic cancellation acceptance.": return "cancel";
            case "Synthetic retry acceptance.": return "retry";
            case "Synthetic retained-history acceptance.": return "retained";
            default: return null;
        }
    }

    private static void Json(NetworkStream stream, int status, string payload)
    {
        Write(stream, "HTTP/1.1 " + status + " " + (status == 200 ? "OK" : "Refused") + "\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: " + Encoding.UTF8.GetByteCount(payload) + "\r\n\r\n" + payload);
    }
    private static void Write(NetworkStream stream, string payload)
    {
        byte[] data = Encoding.UTF8.GetBytes(payload);
        stream.Write(data, 0, data.Length);
        stream.Flush();
    }
}
