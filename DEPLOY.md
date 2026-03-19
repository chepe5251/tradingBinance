# Despliegue en VPS

## Requisitos del servidor

- Ubuntu 20.04+ / Debian 11+ (recomendado)
- 1 GB RAM mínimo (2 GB recomendado)
- Docker + Docker Compose instalados

---

## 1. Instalar Docker (si no está instalado)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## 2. Clonar el repositorio

```bash
git clone https://github.com/chepe5251/tradingBinance.git
cd tradingBinance
```

---

## 3. Configurar credenciales

```bash
cp .env.example .env
nano .env
```

Rellenar obligatoriamente:

```env
BINANCE_API_KEY=tu_api_key
BINANCE_API_SECRET=tu_api_secret
BINANCE_TESTNET=false
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
```

> **Importante:** la IP del VPS debe estar en la whitelist de la API key de Binance.
> Puedes ver la IP pública del VPS con: `curl ifconfig.me`

---

## 4. Arrancar el bot

```bash
docker compose up -d --build
```

---

## 5. Comandos útiles

```bash
# Ver logs en tiempo real
docker logs -f binance_bot

# Ver últimas 100 líneas
docker logs --tail 100 binance_bot

# Ver trades registrados
docker logs -f binance_bot 2>&1 | grep -E "entry|exit|scale|orphan"

# Consultar historial SQLite
sqlite3 logs/trades.db "SELECT symbol, side, entry_price, exit_price, result, pnl FROM trades ORDER BY id DESC LIMIT 20;"

# Detener el bot
docker compose down

# Reiniciar el bot
docker compose restart

# Actualizar a la última versión
git pull
docker compose up -d --build
```

---

## 6. Estructura de logs

| Archivo | Contenido |
|---------|-----------|
| `logs/trades.log` | Cada señal, entrada, escala, salida y evento de monitoreo |
| `logs/trades.db` | Base de datos SQLite con historial completo de trades |

---

## 7. Heartbeat esperado (logs normales)

```
INFO | Scheduler init | symbols=527 intervals=['15m', '1h']
INFO | Scheduler: polling 527 symbols × 2 intervals via REST
INFO | Heartbeat: bot alive | polls=1 last_close=... next_close_in=892s scheduler=True
```

El bot evalúa señales exactamente 4 veces por hora (:00, :15, :30, :45).

---

## 8. Verificar que está operando correctamente

```bash
# El scheduler debe mostrar "True"
docker logs binance_bot 2>&1 | grep "scheduler"

# Deben aparecer filtros de señales cada 15 min
docker logs binance_bot 2>&1 | grep "filter\|signal\|entry\|exit"
```
