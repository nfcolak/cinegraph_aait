# CineGraph (SlateLeapingDeer)

> **A Knowledge-Graph-Powered Multimodal Conversational Movie Agent**  
> Developed as part of the University of Zurich (UZH) AI Core curriculum.

---

## 📌 Overview

**CineGraph** (evaluation codename: `SlateLeapingDeer`) is an intelligent conversational agent engineered to answer complex movie-related questions, infer missing knowledge, recommend films, and provide multimedia assets (posters, actor portraits, scenes).

It operates seamlessly either via the **Speakeasy** chat platform or directly through local CLI interfaces.

---

## 🚀 Key Capabilities

### 1. Robust Factual QA via Knowledge Graph (SPARQL)
- Queries a local RDF knowledge graph (`graph.nt`) mapped from Wikidata using SPARQL.
- Resolves entity names (movies, actors, directors, screenwriters) with typo tolerance and aliases.
- Handles multi-hop and inverse relation questions (e.g., *"Who directed Inception?"*, *"Which movies did Christopher Nolan direct?"*).

### 2. Knowledge Graph Embedding Fallback (KGE)
- When factual links are absent from the graph, CineGraph falls back to pre-trained TransE/ComplEx graph embeddings (`entity_embeds.npy` and `relation_embeds.npy`).
- Predicts missing heads/tails via vector similarity scoring.

### 3. Content-Based Recommendation Engine
- Generates tailored movie suggestions using **Weighted Jaccard Similarity** over graph attributes (genres, directors, cast, release period).
- Supports genre, keyword, language, and production company constraints (e.g., *"Recommend an action movie from Pixar"*).

### 4. Intelligent Multimedia Retrieval
- Automatically identifies user intent for visual media:
  - **Posters**: Film posters for movie requests.
  - **Profiles**: Headshots and portraits for actors/crew members.
  - **Backdrops**: Film scenes and stills.
  - **Actor + Scene**: Specific actors appearing in scenes of a particular movie (e.g., *"Show me Brad Pitt in a scene from Fight Club"*).
- Resolves remote media tokens for instant rendering in chat.

---

## 🛠️ Project Structure

```
.
├── core/
│   ├── data.py          # Graph loaders, embeddings reader & dataset caches
│   ├── entity.py        # Entity matching & alias resolution
│   ├── query.py         # SPARQL query builders & graph traversals
│   ├── recommender.py   # Weighted Jaccard recommendation engine
│   ├── relation.py      # Relation extraction & property mapping
│   └── responser.py     # Main routing, QA coordinator & multimedia pipeline
├── Report/              # Evaluation reports & system documentation
├── agent.py             # Speakeasy bot server with rate-limiting & concurrency control
├── interactive_agent.py # Interactive CLI session for testing queries
├── main.py              # Single-query CLI runner
├── movie_info.py        # Movie detail inspector utility
├── test_backdrop.py     # Tests for scene/backdrop detection
├── test_multimedia.py   # Tests for visual intent & multimedia resolution
└── test_robustness.py   # Stress-testing rate limiters and error handlers
```

---

## 📦 Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/nfcolak/cinegraph_aait.git
cd cinegraph_aait
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

---

## 💻 Usage

### Single-query CLI testing
```bash
python main.py "Who directed 'Fargo'?"
```

### Interactive CLI session
```bash
python interactive_agent.py
```

### Run Speakeasy Bot
```bash
python agent.py
```

---

## 👥 Authors
- **Necati Furkan Çolak**
- **Leyla Khasiyeva**
