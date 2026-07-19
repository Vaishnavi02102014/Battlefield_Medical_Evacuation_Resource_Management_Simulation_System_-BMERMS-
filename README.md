<div align="center">

# 🚑 Battlefield Medical Evacuation Resource Management Simulation System (BMERMS)

**A discrete-event battlefield MEDEVAC simulation, resource management console, and AI decision-support system — built on Streamlit and SQLite.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.51.0-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Status](https://img.shields.io/badge/Status-Production%20Ready-2ea44f?style=flat-square)
![Last Updated](https://img.shields.io/badge/Last%20Updated-July%202026-blue?style=flat-square)

</div>

---

## 📌 Project at a Glance

| | |
|---|---|
| **Language** | Python |
| **Framework** | Streamlit |
| **Database** | SQLite |
| **AI Models** | 3 trained scikit-learn pipelines (transfer, recovery, return-to-duty) |
| **Architecture** | Layered — Frontend → Service Layer → Backend → Database |
| **Interface** | 6-page Streamlit command console |

---

## 🩺 Overview

**BMERMS** is a simulation and command-console system that models the flow of casualties through a battlefield medical evacuation chain — from the moment an incident occurs to a soldier's eventual return to duty.

It exists to give operators, planners, and researchers a live, interactive way to explore how casualty load, transport availability, and facility capacity interact under pressure, without needing real operational data. The system generates its own battlefield incidents and casualties on a virtual clock, routes them through a fixed four-tier evacuation chain (**RAP → ADS → HMV → FDC**), and tracks every bed, vehicle, and medical team involved.

On top of the simulation sits an **AI decision-support layer** — trained on a synthetic battlefield casualty dataset — that predicts evacuation transfer requirements, recovery timelines, and return-to-duty likelihood, and turns those predictions (combined with live resource load) into a single prioritized tactical recommendation.

**Who it's for:**
- Researchers and students exploring MEDEVAC resource-allocation modeling
- Mentors and evaluators reviewing a full-stack simulation + AI system
- Developers who want a reference for a layered Streamlit application (frontend → services → backend → database)

> **NOTE**
> All battlefield locations, unit names, and grid coordinates are fictional. The simulation operates on a synthetic Area of Operations and a synthetic casualty dataset — no real operational or classified data is used.

---

## 🚀 Highlights

- 🎮 Live Battlefield Medical Evacuation Simulation
- 🤖 AI-Assisted Tactical Recommendations
- 🗺️ Interactive Tactical Map
- 🚐 Resource Management
- 🖥️ Multi-page Streamlit Dashboard
- 🗄️ SQLite-backed Simulation

---

## ✨ Key Features

- 🎮 **Live Battlefield Simulation** — a virtual, tick-driven simulation clock (1×/2×/5×/10× speed) that generates incidents and casualties in real time
- 🧍 **Dynamic Casualty Generation** — procedurally generated casualties with rank, unit, age, injury type, and severity
- 🚁 **Medical Evacuation Workflow** — a fixed Scenario → Operation → Incident → Casualty → Decision Engine → Transport → Treatment → Recovery → Return to Duty pipeline
- 🗺️ **Tactical Battlefield Map** — an interactive Folium map showing facilities, incidents, ambulances, helicopters, and medical teams with live layer controls and a legend
- 🏥 **Facility Management** — real-time bed occupancy, queue length, and utilization tracking across all four evacuation-chain facilities
- 🩹 **Patient Management** — a searchable, filterable, sortable patient registry with per-casualty detail and treatment views
- 🚐 **Resource Management** — fleet status for ambulances, helicopters, and medical teams, including dispatch and release logic
- 🤖 **AI Tactical Recommendations** — model-driven predictions combined with a rule-based recommendation engine and confidence scoring
- 📊 **Analytics Dashboard** — KPI summaries, casualty trends, facility load, resource utilization, sector hotspots, and AI model performance
- 🗄️ **SQLite Persistence** — a dedicated, foreign-key-enforced schema for every operational entity
- 🖥️ **Streamlit Interface** — a six-page, service-layered command console with a consistent tactical UI theme

---

## 🏗️ System Architecture

BMERMS follows a strict, layered architecture. Each layer only talks to the layer directly beneath it:

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (Streamlit)                       │
│              app.py  ·  app_pages/  ·  components/               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                          SERVICE LAYER                           │
│                  frontend/services/*_service.py                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                             BACKEND                               │
│ backend/simulation/  ·  backend/ai/  ·  backend/database/crud.py │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SQLITE DATABASE                          │
│                            bmerms.db                             │
└─────────────────────────────────────────────────────────────────┘
```

- **Frontend (Streamlit):** `app.py` is a deliberately minimal entry point — it loads the theme, renders the sidebar and header, and delegates to `utils/page_router.py`. Each page in `app_pages/` owns only layout and presentation.
- **Service Layer:** Each page pulls data through a dedicated service module (`dashboard_service`, `facilities_service`, `patients_service`, `resources_service`, `ai_service`). Pages contain no direct database or AI imports where a service already exists.
- **Backend:** `backend/simulation/` runs the tick-based evacuation engine, `backend/ai/` serves model predictions and recommendations, and `backend/database/crud.py` is the single point of SQL access — no other layer writes raw SQL.
- **SQLite Database:** `bmerms.db` persists every operational entity (facilities, beds, casualties, treatments, queues, and fleets). The Mission Log is the one exception — it is intentionally runtime-only and lives in Streamlit's `session_state`.

---

## 📂 Project Structure

```
DRDO/
├── backend/
│   ├── ai/                       # AI models, feature building, predictions, recommendations
│   │   ├── models/                # Trained pipelines (transfer, recovery, duty)
│   │   ├── feature_builder.py
│   │   ├── predictor.py
│   │   ├── recommendation_engine.py
│   │   ├── resource_assessment.py
│   │   └── train_models.py
│   ├── database/                 # Schema, seeding, and all SQL access
│   │   ├── db.py
│   │   ├── init_db.py
│   │   ├── crud.py
│   │   └── models.py
│   ├── simulation/                # Tick-based evacuation engine
│   │   ├── simulation_controller.py
│   │   ├── simulation_clock.py
│   │   ├── event_generator.py
│   │   ├── casualty_generator.py
│   │   ├── decision_engine.py
│   │   ├── resource_manager.py
│   │   ├── bed_manager.py
│   │   ├── queue_manager.py
│   │   ├── transport_queue.py
│   │   ├── treatment_engine.py
│   │   └── mission_log.py
│   └── utils/                     # Shared config, constants, and helpers
│
├── frontend/
│   ├── app.py                     # Streamlit entry point
│   ├── app_pages/                 # Dashboard, Simulation, Facilities, Patients, Resources, Analytics
│   ├── components/                # Sidebar, header, panels, metric cards, tactical map
│   ├── services/                  # Page ↔ backend data-access layer
│   ├── utils/                     # Theme and page routing
│   └── assets/theme.css           # Global visual theme
│
├── bmerms.db                      # SQLite database (created/seeded automatically on first run)
└── requirements.txt
```

---

## ⚙️ Simulation Workflow

Every casualty in BMERMS moves through the same fixed pipeline, coordinated end-to-end by `simulation_controller.py`:

```
Scenario → Operation → Incident → Casualty → Decision Engine
        → Transport → Treatment → Recovery → Return To Duty
```

| Stage | What happens |
|---|---|
| **Scenario / Operation** | The top-level context a simulation run operates under. |
| **Incident** | `event_generator.py` decides *when* and *where* a battlefield event occurs, and how many casualties it produces. |
| **Casualty** | `casualty_generator.py` generates each casualty's attributes (rank, unit, age, injury type, severity). |
| **Decision Engine** | Applies the fixed severity → priority → facility mapping, then dispatches an ambulance or helicopter and computes real transit time. |
| **Transport** | The casualty is "Being Evacuated" until transit time elapses — resource dispatch genuinely affects simulation timing, it doesn't just flip a status flag. |
| **Treatment** | Once seated, `bed_manager.py` and `treatment_engine.py` run the facility's fixed treatment duration, with dispatched medical teams shaving time off it. |
| **Recovery** | When treatment ends, the casualty is marked **Recovered**, their bed is released, and the next queued casualty is promoted. |
| **Return to Duty** | After a scheduled outprocessing delay, status finalizes to **Returned to Duty**. |

Each simulation tick (driven by the Simulation page's auto-refresh loop) advances the clock, releases completed transport, admits arrived evacuations, completes due treatments, refreshes queue wait times, possibly spawns a new incident, and evaluates medical-team surge dispatch — in that order.

---

## 🤖 AI Module

The AI module is a self-contained decision-support layer trained on the included synthetic battlefield casualty dataset. It never touches the database, simulation engine, or frontend directly — everything flows through plain dictionaries.

```
Live simulation state (dict)
        │
        ▼
Feature Builder  ──►  translates raw state into model-ready features
        │
        ▼
Prediction Models  ──►  three independent RandomForest pipelines
        │
        ▼
Recommendation Engine  ──►  combines predictions + resource load
        │
        ▼
Single, prioritized, human-readable recommendation + confidence score
```

- **Feature Builder** (`feature_builder.py`) — Converts a live simulation-state dictionary into the exact feature format each model expects, defensively defaulting any missing values.
- **Prediction Models** (`predictor.py`, `backend/ai/models/*.pkl`) — Three trained `scikit-learn` pipelines:
  - `transfer_model.pkl` — predicts whether an evacuation **transfer** will be required
  - `recovery_model.pkl` — predicts **recovery days**
  - `duty_model.pkl` — predicts **return-to-duty** likelihood
- **Recommendation Engine** (`recommendation_engine.py`) — A rule-based layer that combines model predictions with a centralized, weighted **resource load assessment** (occupancy, queue length, critical casualties, available resources) to produce one prioritized recommendation, evaluated in priority order.
- **Confidence Scoring** — Every recommendation carries a numeric confidence score, built from a base confidence per rule, a corroboration bonus when the model prediction agrees with the resource signal, and clamped floors/ceilings so scores stay in a meaningful, bounded range.
- **AI Decision Flow** — The recommendation engine is defensive by design: if a model fails to load or a prediction fails, it falls back to a neutral prediction/assessment rather than raising, so the operator always sees a recommendation.

Models are trained offline via `backend/ai/train_models.py` and served through a lazy, cached `model_loader.py` — nothing is retrained at runtime.

---

## 🗄️ Database Overview

BMERMS persists its operational state in a single SQLite database (`bmerms.db`), managed exclusively through `backend/database/crud.py`. The schema covers:

| Table | Purpose |
|---|---|
| `Facilities` | The four fixed evacuation-chain facilities and their live capacity/occupancy |
| `Beds` | Individual bed status per facility |
| `Scenarios` / `Operations` | Top-level simulation context |
| `Incidents` | Generated battlefield events |
| `Casualties` | Every casualty and their current status, priority, and evacuation state |
| `Treatments` | Treatment start/end and duration per casualty |
| `Waiting_Queue` | Casualties queued for a bed, ordered by priority |
| `Ambulances` / `Helicopters` | Transport fleet status and current assignment |
| `Medical_Teams` | Surge medical team status and facility assignment |

> **IMPORTANT**
> The Mission Log is deliberately **not** part of this schema — it lives only in Streamlit's session state for the duration of a run, per the system's approved architecture.

---

## 🖥️ Application Pages

| Page | What it shows |
|---|---|
| **Dashboard** | Operational snapshot — a 6-card KPI row, evacuation workflow strip, live Battlefield Map, and asset inventory |
| **Simulation** | The operator console — simulation controls, manual incident generation, the live Battlefield Map, AI Tactical Recommendation, current operation, transport queue, resource/facility status, and Mission Log |
| **Facilities** | KPI summary, a searchable/sortable Operational Facility Overview table, and a Facility Detail panel (status, capacity, operations) |
| **Patients** | A searchable/filterable Patient Registry with severity/priority/status color coding, a Patient Detail panel, and a Current Treatment panel |
| **Resources** | Fleet status, medical team status, resource allocation, dispatch timeline, and resource availability |
| **Analytics** | KPI summary, casualty trend analysis, facility load analysis, resource utilization, sector hotspots, triage severity distribution, and AI model performance |

---

## 🛠️ Technologies Used

| Technology | Role |
|---|---|
| **Python** | Core language for the entire backend and frontend |
| **Streamlit** | Web application framework powering the UI |
| **SQLite** | Embedded relational database for all persisted state |
| **Pandas** | Data manipulation across services, pages, and AI training |
| **Plotly** | Charts and KPI visualizations across the Dashboard, Resources, and Analytics pages |
| **Folium / streamlit-folium** | Interactive tactical battlefield map rendering |
| **Scikit-learn** | Training and serving the transfer, recovery, and duty prediction models |
| **Joblib** | Serializing and loading trained model pipelines |
| **streamlit-autorefresh** | Drives the simulation's live tick loop |

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/Vaishnavi02102014/Battlefield_Medical_Evacuation_System.git
cd Battlefield_Medical_Evacuation_System

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the application
streamlit run frontend/app.py
```

> **TIP**
> The SQLite database (`bmerms.db`) and its schema are created and seeded automatically on first launch — no manual database setup is required.

---

## ⚡ Quick Start

```bash
pip install -r requirements.txt
streamlit run frontend/app.py
```

---

## 📦 Requirements

All dependencies are listed in [`requirements.txt`](./requirements.txt).

---

## 📸 Screenshots

<!-- Add screenshots to a docs/screenshots (or similar) folder and update the paths below. -->

| Dashboard | Simulation |
|:---:|:---:|
| *placeholder* | *placeholder* |
| Operational snapshot — KPIs, evacuation workflow, and Battlefield Map | Live operator console — simulation controls and tactical map |

| Facilities | Patients |
|:---:|:---:|
| *placeholder* | *placeholder* |
| Facility overview table and Facility Detail panel | Patient registry and Current Treatment panel |

| Resources | Analytics |
|:---:|:---:|
| *placeholder* | *placeholder* |
| Fleet, medical team, and resource availability status | KPIs, trends, and AI model performance |

---

## 🔄 Typical Workflow

1. Launch the app — the Dashboard shows the current operational snapshot.
2. Go to **Simulation** and start the clock; incidents and casualties begin generating automatically (or trigger one manually via the Manual Incident Generator).
3. Watch the Decision Engine triage each casualty, dispatch transport, and route them to the correct facility on the live Battlefield Map.
4. Follow casualties through treatment, recovery, and return to duty in the Mission Log and on the **Patients** page.
5. Monitor fleet and medical team load on the **Resources** page, and facility occupancy on the **Facilities** page.
6. Check the **AI Tactical Recommendation** panel for a live, confidence-scored suggestion based on current load.
7. Review trends and system-wide performance on the **Analytics** page.

---

## 📈 Future Extensibility

The layered architecture — frontend pages, a dedicated service layer, an independent simulation engine, and a self-contained AI module — means each layer can evolve independently. New pages can be added purely by registering a route in `page_router.py`; new AI models can be trained and swapped in through `model_loader.py` without touching the simulation engine; and new resource types or facilities can be introduced through `backend/utils/constants.py` without modifying business logic elsewhere.

---

## 👨‍💻 Author
**Vaishnavi Upadhyay**

---

