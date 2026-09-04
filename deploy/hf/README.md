---
title: ProductChat Demo
emoji: 🔔
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: AI product assistant demo for the Metzler shop
---

# ProductChat — demo

AI product-recommendation assistant (RAG) for the Metzler shop. Retrieval runs on
Mistral embeddings; answers on Groq. This Space builds itself from
[github.com/SabaVafa/ProductChat](https://github.com/SabaVafa/ProductChat) and the
`demo-seed` release asset.

**Open the chat demo at `/widget-demo`** (append it to the Space's app URL).

Set these as Space **secrets** (Settings → Variables and secrets):
`GROQ_API_KEY`, `MISTRAL_API_KEY`, `ADMIN_TOKEN`, `ENCRYPTION_KEY`.
