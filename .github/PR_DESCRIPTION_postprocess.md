**Resumo das alterações aplicadas**

- Treinei calibradores isotónicos usando histórico gerado via proxy e salvei em `models/calibrators/`.
- Adicionei scripts utilitários para aplicar postprocess em modo seguro, comparar versões e reavaliar extremos:
  - `scripts/apply_postprocess_safe.py`
  - `scripts/compare_and_replace_postprocess.py`
  - `scripts/revaluate_and_replace.py`
  - `scripts/fetch_historical_results.py` (fetch via proxy)
- Ajustei `scripts/train_isotonic_calibrators.py` (correção `global MIN_SAMPLES`).
- Apliquei o postprocess seguro e, após reavaliação com thresholds mais razoáveis (<=0.005 / >=0.995), substituí `data/predict/predictions.json` com backup criado em `backups/`.

**Por que isto é seguro**
- Todos os passos são reprodutíveis por scripts no repositório.
- Antes de substituir a produção foi gerada uma versão segura em `tmp/postprocess_applied.json` e comparada com heurística (extremos + cobertura `v2`).
- Backup automático salvo em `backups/predictions.json.bak.<timestamp>`.

**Pontos de revisão / atenção**
- Verificar `tmp/postprocess_applied_audit_by_league.csv` para ligas críticas.
- Confirmar que os calibradores gerados (em `models/calibrators/`) são aceitáveis; muitas ligas têm poucos dados e não gerámos calibradores para elas.
- Se preferires limites menos permissivos, posso ajustar clamps (`MIN_P` / `MIN_PB` em `src/pipeline/v2_postprocess.py`) e re-aplicar.

**Comandos para reproduzir**
```powershell
python .\scripts\fetch_historical_results.py --from 2024-08-01 --to 2025-08-31
python .\scripts\train_isotonic_calibrators.py --csv data\train\historico_com_probs.csv
python .\scripts\apply_postprocess_safe.py
python .\scripts\revaluate_and_replace.py --low 0.005 --high 0.995 --apply
```

**Sugestão**: Revisão manual rápida dos `tmp/*` artefactos e, se OK, aprovar o PR para merge.
