# Model backends: LM Studio and OpenRouter by hand

`ygg install` configures all of this for you. This page is for scripted setups and for when something 404s.

## LM Studio: the four things that catch people out

`ygg install` handles all of this. Read on only if you're wiring it by hand.

**1. Two settings, two different shapes of the same URL.** `embed_url` is the
`/v1` base; `distill_url` is the host root. Same server, and swapping them gets
you a 404 that reads like the endpoint is simply wrong.

```bash
ygg config set embed_backend openai
ygg config set embed_url    http://127.0.0.1:1234/v1
ygg config set distill_url  http://127.0.0.1:1234
```

**2. The model id is not what you downloaded.** `lms get nomic-embed-text` puts
a model on disk that the API answers to as
`text-embedding-nomic-embed-text-v1.5`. Ask the server, don't guess:

```bash
curl -s http://127.0.0.1:1234/api/v0/models | grep '"id"'
```

**3. Turn on Just-In-Time model loading** (Developer tab). Without it nothing is
loaded when the daemon calls, and every request 404s.

**4. Turn on "run the server on login".** The Yggdrasil daemon starts at boot; if
LM Studio's server doesn't, dense search silently degrades to lexical until you
next open the app.


## OpenRouter: two settings that will bite you

**1. Use an inference key, not a provisioning key.** Keys from
[openrouter.ai/settings/provisioning-keys](https://openrouter.ai/settings/provisioning-keys)
can only mint other keys — embedding calls with one return a baffling
`401 User not found`. Create a normal key at
[openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) instead.

Note that `GET /api/v1/models` answers `200 OK` for *any* key, valid or not —
it ignores auth entirely, so it can't tell you whether your key works. Check
`GET /api/v1/key` instead: it returns `is_provisioning_key`, and fails outright
on a bad key.

**2. Privacy settings silently hide most models.** If a model 404s with
`All providers have been ignored`, the model is fine — your account is
filtering out every provider that serves it. Fix it at
[openrouter.ai/settings/privacy](https://openrouter.ai/settings/privacy).
That filter is also why `openai/text-embedding-3-*` can come back `403` on a
provider's terms of service.

Browse what's actually available at
[openrouter.ai/models?output_modalities=embeddings](https://openrouter.ai/models?fmt=cards&output_modalities=embeddings)
(26 models at the time of writing). Useful ones:

| Model | Price / 1M tokens |
| --- | --- |
| `nvidia/llama-nemotron-embed-vl-1b-v2:free` | **$0** |
| `perplexity/pplx-embed-v1-0.6b` | $0.004 |
| `intfloat/multilingual-e5-large` | $0.01 — multilingual |
| `google/gemini-embedding-2` | $0.20 |
