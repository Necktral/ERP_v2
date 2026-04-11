#!/usr/bin/env bash
set -euo pipefail

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS | $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL | $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

echo "== Codex + Lucid MCP doctor =="

echo "[1/6] Entorno WSL"
if uname -a | grep -qi microsoft; then
  pass "Kernel WSL detectado"
else
  fail "No se detecta WSL en el kernel"
fi

echo "[2/6] Codex en PATH"
if command -v codex >/dev/null 2>&1; then
  pass "codex disponible en PATH: $(command -v codex)"
elif [ -x "$HOME/.local/bin/codex" ]; then
  pass "codex instalado en usuario: $HOME/.local/bin/codex"
else
  fail "codex no esta instalado o no esta en PATH"
fi

echo "[3/6] Config Codex"
CONFIG_FILE="$HOME/.codex/config.toml"
if [ -f "$CONFIG_FILE" ]; then
  pass "Existe $CONFIG_FILE"
else
  fail "No existe $CONFIG_FILE"
fi

echo "[4/6] Bloque Lucid MCP"
if grep -q "\[mcp_servers.lucid\]" "$CONFIG_FILE" \
  && grep -q 'url = "https://mcp.lucid.app/mcp"' "$CONFIG_FILE"; then
  pass "Bloque Lucid MCP correcto"
else
  fail "Bloque Lucid MCP ausente o URL incorrecta"
fi

echo "[5/6] Estado OAuth"
CODEX_BIN="codex"
if ! command -v codex >/dev/null 2>&1; then
  CODEX_BIN="$HOME/.local/bin/codex"
fi

MCP_LIST_OUTPUT="$($CODEX_BIN mcp list 2>/dev/null || true)"
echo "$MCP_LIST_OUTPUT"
if echo "$MCP_LIST_OUTPUT" | grep -Eq '^lucid\s+https://mcp\.lucid\.app/mcp\s+.*\s+enabled\s+OAuth$'; then
  pass "Lucid autenticado por OAuth"
elif echo "$MCP_LIST_OUTPUT" | grep -Eq '^lucid\s+https://mcp\.lucid\.app/mcp\s+.*\s+enabled\s+Not logged in$'; then
  fail "Lucid aun no esta autenticado"
else
  fail "No se pudo determinar estado de autenticacion de Lucid"
fi

echo "[6/6] Reachability HTTPS"
HTTP_CODE="$(curl -sS -o /dev/null -m 12 -w '%{http_code}' https://mcp.lucid.app/mcp || true)"
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "405" ]; then
  pass "Endpoint Lucid MCP reachable (HTTP $HTTP_CODE)"
else
  fail "Endpoint Lucid MCP no alcanzable o respuesta inesperada (HTTP ${HTTP_CODE:-n/a})"
fi

echo
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo "Resultado: $PASS_COUNT/$TOTAL checks en PASS"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "Estado final: REQUIERE ATENCION"
  exit 1
fi

echo "Estado final: OK"
