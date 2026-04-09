# Claw-ED Architecture Diagrams

Visual reference for the core systems. All diagrams use Mermaid syntax.

---

## 1. Message Flow

How a user message travels from transport to response.

```mermaid
flowchart LR
    User([User])

    subgraph Transports
        CLI[CLI Transport]
        TG[Telegram Bot]
        Web[Web API]
        Hermes[Hermes/OpenClaw]
    end

    GW[Gateway<br/>core.py]

    subgraph Control Plane
        Onboard[OnboardHandler]
        Ingest[IngestHandler]
        Export[ExportHandler]
        Models[/models command/]
    end

    subgraph Agent Loop
        Prompt[build_system_prompt]
        Memory[Memory Loader<br/>3-layer context]
        Loop[run_agent_loop]
        LLM[LLM Adapter<br/>Anthropic / OpenAI /<br/>Ollama / OpenRouter]
        Tools[ToolRegistry<br/>40+ tools]
    end

    Resp([GatewayResponse])

    User --> CLI & TG & Web & Hermes
    CLI & TG & Web & Hermes --> GW

    GW -->|files attached| Ingest
    GW -->|onboarding active| Onboard
    GW -->|/models| Models
    GW -->|natural language| Prompt

    Prompt --> Memory
    Memory --> Loop
    Loop <-->|tool calls| Tools
    Loop <-->|generate| LLM

    Ingest --> Resp
    Onboard --> Resp
    Models --> Resp
    Loop --> Resp

    Resp --> User
```

---

## 2. Data Storage

Which databases store what, and where they live on disk.

```mermaid
flowchart TB
    subgraph "~/.eduagent/"
        ConfigJSON[config.json<br/>API keys, provider,<br/>teacher profile]
        SecretsJSON[secrets.json<br/>Encrypted credentials]
        StateDB[(state.db<br/>SQLite)]
        BotStateDB[(bot_state.db<br/>SQLite)]

        subgraph memory/
            CurrKB[(curriculum_kb.db<br/>SQLite)]
        end

        subgraph workspace/
            IdentityMD[identity.md]
            SoulMD[soul.md]
            MemoryMD[memory.md]
            HeartbeatMD[heartbeat.md]
            NotesDir[notes/]
        end
    end

    subgraph "clawed_data/"
        ClawedDB[(clawed.db<br/>SQLite)]
    end

    StateDB -->|conversation state| S1[TeacherSession]
    StateDB -->|class codes| S2[Classes & students]
    StateDB -->|student questions| S3[StudentBot state]

    BotStateDB -->|Telegram sessions| B1[Bot persistence]

    CurrKB -->|text chunks| K1[Curriculum KB]
    CurrKB -->|asset registry| K2[File metadata + images]
    CurrKB -->|knowledge graph| K3[Entities + triples]
    CurrKB -->|episodic memory| K4[Teacher interactions]
    CurrKB -->|wiki articles| K5[Compiled curriculum wiki]
    CurrKB -->|embeddings| K6[Semantic vectors]
    CurrKB -->|session turns| K7[Cross-transport history]

    ClawedDB -->|lessons| D1[Generated lesson plans]
    ClawedDB -->|units| D2[Unit plans]
    ClawedDB -->|feedback| D3[Teacher ratings]
    ClawedDB -->|teachers| D4[Teacher profiles]
```

---

## 3. Ingestion Pipeline

The `full_ingest()` path from raw files to searchable knowledge.

```mermaid
flowchart TD
    Input[/"Teacher's files<br/>(PDF, DOCX, PPTX, TXT,<br/>NOTEBOOK, XBK, Flipchart)"/]

    subgraph "Step 1: Parse"
        Collect[_collect_files<br/>recursive glob]
        Detect[_detect_type<br/>extension map]
        Extract[_extract_single<br/>per-format extractor]
        Docs[List of Document objects]
    end

    subgraph "Step 2-3: Assets"
        ExtractRich[extract_rich<br/>images + URLs + YouTube]
        Register[AssetRegistry.register_asset<br/>file-level metadata]
    end

    subgraph "Step 4: Chunks"
        KB[CurriculumKB.index<br/>split into chunks<br/>+ embeddings]
    end

    subgraph "Step 5: Knowledge Graph"
        Entities[extract_entities_from_document]
        Rels[infer_relationships]
        KG[CurriculumKG<br/>add_entity + add_triple]
        Embed[batch_embed_unembedded]
    end

    subgraph "Step 6: Wiki"
        Wiki[compile_wiki<br/>LLM-powered article synthesis]
    end

    Result[/"full_ingest result dict<br/>docs_parsed, assets_registered,<br/>images_extracted, chunks_indexed,<br/>kg_entities, kg_triples,<br/>wiki_articles, errors"/]

    Input --> Collect --> Detect --> Extract --> Docs
    Docs --> ExtractRich --> Register
    Docs --> KB
    Docs --> Entities --> Rels --> KG --> Embed
    Docs --> Wiki

    Register --> Result
    KB --> Result
    Embed --> Result
    Wiki --> Result
```

---

## 4. Lesson Generation Pipeline

From a teacher request to the 9 compiled output files.

```mermaid
flowchart TD
    Request["Teacher: 'Make a lesson<br/>on the water cycle for 7th grade'"]

    subgraph "1. Context Gathering"
        Search[search_my_materials<br/>CurriculumKB.search]
        Standards[search_standards<br/>state standards lookup]
        KGQuery[KG entity lookup<br/>related concepts]
        Profile[Teacher profile<br/>+ persona + preferences]
    end

    subgraph "2. LLM Generation"
        SysPrompt[System prompt<br/>+ teacher context<br/>+ curriculum hits<br/>+ standards]
        LLMCall[LLM generate<br/>structured output]
        MC[MasterContent<br/>Pydantic model]
    end

    subgraph "3. Image Pipeline"
        TeacherImg[_resolve_from_teacher_assets<br/>local images first]
        WebImg[_fetch_one<br/>external image search]
        ImgMap["images: dict[spec, Path]"]
    end

    subgraph "4. Compilation"
        Slides[compile_slides<br/>PPTX with images]
        Teacher[compile_teacher_view<br/>teacher lesson plan]
        Student[compile_student_view<br/>student packet]
        Game[compile_game<br/>interactive HTML game]
        Sim[compile_simulation<br/>interactive simulation]
        Journey[compile_journey<br/>learning journey map]
        SubPkt[sub_packet<br/>differentiated materials]
        DocExport[export_docx / export_pdf<br/>document exports]
        Handout[export_handout<br/>printable handout]
    end

    Output[/"9 Output Files<br/>slides.pptx<br/>teacher_plan.md<br/>student_packet.md<br/>game.html<br/>simulation.html<br/>journey.html<br/>sub_packet.md<br/>lesson.docx / .pdf<br/>handout.pdf"/]

    Request --> Search & Standards & KGQuery & Profile
    Search & Standards & KGQuery & Profile --> SysPrompt
    SysPrompt --> LLMCall --> MC

    MC --> TeacherImg
    TeacherImg -->|remaining| WebImg
    TeacherImg --> ImgMap
    WebImg --> ImgMap

    MC --> Slides & Teacher & Student & Game & Sim & Journey & SubPkt & DocExport & Handout
    ImgMap --> Slides

    Slides & Teacher & Student & Game & Sim & Journey & SubPkt & DocExport & Handout --> Output
```
