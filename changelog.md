# 📝 CHANGELOG

## [2026-06-27] - The Ponytail Weekend Clean-up
### Removed
- Dropped useless SMC Order Block logic from `feature_builder.py` and `indicator_math.py` (noise reduction).
- Added logic in `ml_lightgbm.py` to drop `is_near_ob`, `dist_to_bull_ob`, and `dist_to_bear_ob` before training.

### Added
- `core/config.py` for centralized settings (Ollama URL, LGBM configs, etc.) without requiring `python-dotenv`.
- `intelligence/llm_macro_agents.py` (Phase 5) to asynchronously fetch Yahoo Finance RSS and get Bullish/Bearish bias from DeepSeek.
- Added logic in `orchestration/main_loop.py` to read `macro_state.json` and embed `macro_bias` directly into the `features_json` of every snapshot.
- `export_csv.py` for a 1-click dump of the database to CSV.

### Fixed
- Fixed syntax error in `main_loop.py` (`features=features),`) and removed hardcoded references to the deleted OB features that would have crashed the bot on Monday.
