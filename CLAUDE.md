# Industrial Brain OS

## Project Mission

Industrial Brain OS is a research-grade AI platform being built for an Industrial Knowledge Intelligence hackathon.

The goal is to create a unified AI-powered Asset & Operations Brain that ingests heterogeneous industrial documents (engineering drawings, P&IDs, SOPs, manuals, maintenance records, inspection reports, work orders, regulations, emails and spreadsheets) and transforms them into an enterprise knowledge platform.

The platform will ultimately provide:

* Universal document ingestion
* Industrial ontology
* Knowledge Graph
* Hybrid GraphRAG
* Expert Engineering Copilot
* Maintenance Intelligence
* Root Cause Analysis
* Regulatory Compliance Intelligence
* Lessons Learned Intelligence

This is not a hackathon prototype. Every implementation should be production-grade, modular, secure and scalable.

## Source of Truth

Architecture:
docs/industrial_brain_architecture_v2.md

Engineering Rules:
docs/engineering_bible.md

Architecture Decisions:
docs/architecture_decision_records.md

These documents are authoritative.

Never redesign the architecture.

## Engineering Rules

* Follow Clean Architecture.
* Follow SOLID.
* Follow Domain Driven Design.
* Keep modules loosely coupled.
* Never hardcode secrets.
* Never skip testing.
* Verify every milestone before committing.
* One milestone per session.
* Commit and push after milestone completion.
* Stop after successful verification.

# Repo Intelligence

This repository uses RepoWise.

When reasoning about architecture or implementation:

- Prefer RepoWise-generated documentation.
- Use generated onboarding pages before scanning the entire repository.
- Use dependency graphs and module documentation for navigation.
- Avoid re-reading unchanged files when RepoWise documentation already answers the question.