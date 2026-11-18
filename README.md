# BotDeck

Soukromý panel pro Python Discord boty na Raspberry Pi 4 s 4 GB RAM a Debianem 13.
FastAPI, obyčejné HTML/CSS/JavaScript a Docker Compose; bez databáze nebo Node.js na malině.

## Co první verze umí

- Přehled registrovaných botů, stavu kontejnerů, doby běhu, CPU a RAM.
- Celková RAM hostitele a minutová systémová zátěž z hostitelského `/proc`.
- Start, stop a restart jednotlivého existujícího kontejneru s potvrzením.
- Posledních 200 řádků logů (nejvýše 128 KiB), obnova otevřených logů každé 3 sekundy.
- Odkaz na vlastní dashboard bota; jeho URL musí být dostupné také ze zařízení s prohlížečem.
- Automatická aktualizace přehledu každých 15 sekund, přihlášení jménem a heslem.

**Běžící kontejner neznamená připojeného Discord bota.** Discord stav se proto zobrazuje
jako neověřený. Budoucí heartbeat může dodat skutečnou latenci, počet serverů a stav připojení.
Docker healthcheck se interně načítá, ale není vydáván za připojení k Discordu.
Tato verze nevytváří, nemaže ani neaktualizuje kontejnery přes web. Boty se nasazují přes Compose.
Historie metrik, upozornění a editace tajných údajů přes web nejsou součástí první verze.

## Oddělení od stávajícího projektu

```text
Tvoje zařízení → Tailscale HTTPS → 127.0.0.1:8095
                                      │
                             dashboard (bez socketu)
                                      │ privátní Docker síť + token
                                    agent
                                      │ Docker socket
                    pouze boti v registru se správnými štítky

Compose botdeck       = dashboard + agent
Compose botdeck-bots  = nové boty
Existující projekt   = vlastní Compose, sítě a data
```

Agent pro každé čtení logů a ovládání kontroluje zároveň registr `config/bots.json`,
`com.docker.compose.project=botdeck-bots`, `cz.botdeck.managed=true` a odpovídající
`cz.botdeck.bot-id`. Jednorázové `compose run` kontejnery odmítá. Duplicitní identita operaci zablokuje.
Nespoléhá pouze na jméno kontejneru dodané z prohlížeče.

**Tohle je aplikační omezení, nikoli bezpečnostní hranice Docker démona.** Agent má Docker socket,
tedy technicky silná oprávnění nad celým hostitelem; kompromitovaný agent by mohl zasáhnout další projekt.
Dashboard socket nemá, agent nemá publikovaný port a je na oddělené interní síti.
Pokud potřebuješ izolaci i proti kompromitovanému agentovi, je nutný samostatný Docker daemon
(například rootless pro boty, se zvlášť ověřenou konfigurací) nebo jiný hostitel.

Oba projekty stále sdílejí CPU, RAM, disk a kernel. Proto jsou nastavené limity a rotace logů,
ale bez znalosti stávající zátěže nelze slíbit nulový vliv. Tento repozitář nemění konfiguraci
Docker démona, nestartuje ani nezastavuje jiné Compose projekty a neobsahuje globální úklid Dockeru.

## 1. Kontrola maliny před nasazením

Na malině nejprve proveď pouze tyto informační příkazy:

```bash
uname -m
docker version
docker compose version
docker compose ls
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
free -h
df -h /
sudo ss -lntp
```

Počítá se s 64bit ARM (`aarch64`), Docker Engine a Compose v2. Samotný výpis Debianu
nepotvrzuje architekturu. Na 32bit systému nejprve ověř dostupnost potřebných image.
Ověř, že projektová jména `botdeck` a `botdeck-bots` ani port `8095` už nepoužíváš.
Pokud je port obsazený, změň pouze `BOTDECK_PORT` v `.env` a odpovídající port Tailscale Serve.
Používáš-li Docker přes `sudo`, použij ho konzistentně i v příkazech níže.

## 2. Příprava a spuštění panelu

Zkopíruj tento repozitář do nové samostatné složky na malině, například `~/services/botdeck`.
Následující příkazy spusť v této složce. Nevkládej soubory do existujícího projektu.

```bash
python3 scripts/init_config.py
docker compose -p botdeck -f compose.yaml config --quiet
docker compose -p botdeck -f compose.yaml up -d --build
docker compose -p botdeck -f compose.yaml ps
curl --fail http://127.0.0.1:8095/healthz
```

Inicializace vytvoří `.env` se dvěma různými náhodnými tajnými hodnotami a prázdný registr botů.
Existující soubory nepřepisuje. Přihlašovací jméno je `admin`; heslo najdeš lokálně v `.env`
pod `BOTDECK_PASSWORD`. `.env`, registry a tokeny necommituj. Docker `.env` a env proměnné nejsou
trezor: uživatel s oprávněním k Dockeru si je může přečíst. Nenahrávej Discord tokeny do tohoto chatu.

První sestavení image na Pi může chvíli trvat a dočasně zatížit CPU/RAM.
Panel a agent mají každý maximálně 192 MB RAM a 0,5 CPU. Jde o stropy, nikoli rezervace.
Začni jedním botem s limitem 256 MB / 0,5 CPU a sleduj, kolik potřebuje stávající projekt.
Součet limitů plánuj podle reálné volné RAM; ponech prostor systému a existujícím službám.

Panel poslouchá na hostiteli pouze na `127.0.0.1`, přes LAN se tedy přímo neotevře.
`/healthz` ověřuje webový proces; přihlášený přehled navíc ověřuje komunikaci s Dockerem.

## 3. Soukromý přístup přes Tailscale

Výchozí varianta je oficiální Tailscale klient na malině a na tvém počítači/mobilu.
Použij [oficiální postup pro Linux](https://tailscale.com/download/linux).
Instalace VPN mění síťové nastavení hostitele; pokud stávající projekt používá VPN nebo speciální
pravidla směrování, nejprve ověř jejich kompatibilitu. Zde VPN automaticky neinstalujeme.

Po instalaci klienta:

```bash
sudo tailscale up
sudo tailscale serve --bg http://127.0.0.1:8095
tailscale serve status
```

Dokonči přihlášení podle odkazu klienta a případně povol HTTPS v tailnetu.
Otevři **HTTPS adresu vypsanou Serve** ze zařízení připojeného do stejného tailnetu.
Potom se přihlas údaji z `.env`. Omez tailnetová přístupová pravidla na svůj účet/zařízení.
Basic přihlášení používej vzdáleně přes toto HTTPS; bez něj není heslo chráněné TLS.
Serve poskytuje soukromý přístup, viz [dokumentace](https://tailscale.com/docs/features/tailscale-serve).
Před konfigurací ověř `tailscale serve status`, pokud by na zařízení mezitím vznikla jiná konfigurace.

Zkontroluj dostupnost s VPN a nedostupnost po vypnutí VPN na klientovi.
Neotvírej porty routeru a nezapínej veřejný Tailscale Funnel.
Pokud port není 8095, uprav i příkaz Serve.

### Alternativa: NetBird

Panel není závislý na konkrétní VPN. Můžeš místo Tailscale použít
[NetBird klienta pro Raspberry Pi](https://docs.netbird.io/get-started/install/raspberrypi).
Pro první přístup bez úprav portů či firewallu panelu lze přes NetBird použít SSH tunel:

```bash
ssh -N -L 8095:127.0.0.1:8095 uzivatel@NETBIRD_IP_MALINY
```

Pak otevři `http://127.0.0.1:8095` na svém počítači. Pro přímou VPN URL je potřeba samostatně
navrhnout HTTPS proxy a omezení přístupu; pouhé publikování Docker portu na `0.0.0.0` nepoužívej.
Neinstaluj obě VPN současně jen kvůli tomuto projektu.

## 4. Přidání prvního Python bota

V `config/bots.json` může být například:

```json
[
  {
    "id": "example",
    "name": "Můj Discord bot",
    "description": "Python • discord.py",
    "dashboard_url": null
  }
]
```

Registr se načítá při každém požadavku, změna nevyžaduje restart panelu.
V ukázce nahraď `examples/python-bot/bot.py` vlastním kódem a v Dockerfile doplň jeho závislosti.
Ukázkový bot se pouze připojí k Discordu a zapíše připojení do logu; neobsahuje příkazy.
V `examples/python-bot/.env` vytvoř položku `DISCORD_TOKEN` podle tamního `.env.example`.

```bash
docker compose --project-directory examples/python-bot -p botdeck-bots -f examples/python-bot/compose.yaml config --quiet
docker compose --project-directory examples/python-bot -p botdeck-bots -f examples/python-bot/compose.yaml up -d --build
```

Před nasazením musí sedět ID v registru a štítku `cz.botdeck.bot-id`. Bez kontejneru panel
ukazuje „Nenasazen“. Tlačítko Spustit startuje existující zastavený kontejner; nevytváří ho.
Python image se při sestavení na ARM64 Pi vybere pro danou architekturu; vlastní nativní
závislosti botů musí ARM64 podporovat také.

Další boty přidej jako další služby do **jednoho** Compose souboru s projektem `botdeck-bots`,
každému dej vlastní unikátní ID, image, token a případné datové volume.
Nespouštěj několik nezávislých Compose souborů pod stejným názvem projektu.
Botí síť je oddělená od řídicí sítě a má přístup ven kvůli Discordu.
Pro trvalá data přidej vlastní pojmenované volume a zajisti práva pro UID 10001;
kořenový filesystem ukázkového bota je jen pro čtení.

### Bot s vlastním dashboardem

Do `dashboard_url` patří HTTPS URL dostupná z tvého prohlížeče, například další privátní adresa
Tailscale Serve. Botův web publikuj na samostatný loopback port, třeba
`127.0.0.1:8096:3000`, a zpřístupni ho samostatným Serve listenerem:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8096
```

Použij URL s portem 8443 vypsanou příkazem a omez její přístupová pravidla také.
Hlavní panel botův web pouze otevírá; nenahrazuje jeho přihlášení ani ho automaticky nepublikuje.

## Údržba pouze tohoto projektu

```bash
docker compose -p botdeck -f compose.yaml logs --tail=100 dashboard agent
docker compose -p botdeck -f compose.yaml up -d --build
docker compose -p botdeck -f compose.yaml stop
```

Pro úplné odstranění panelových kontejnerů a jeho sítě použij pouze
`docker compose -p botdeck -f compose.yaml down` ve správné složce. Boty to nezastaví.
Nepoužívej globální `docker system prune`, hromadné zastavování kontejnerů ani restart Docker démona.
Zálohuj `.env`, `config/bots.json`, Compose soubory a případná botí datová volumes bezpečně mimo Pi.
Závislosti jsou omezené kompatibilními rozsahy; po sestavení je ověřuj a změny nasazuj cíleně,
neprováděj automatické aktualizace všech kontejnerů na hostiteli.

## Lokální ověření bez maliny

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Ve Windows použij `.venv\Scripts\python.exe` namísto `.venv/bin/python`.
Testy simulují Docker API a ověřují odmítnutí cizích kontejnerů, duplicitních identit,
nepřihlášeného přístupu, nebezpečných URL a cross-site operací. Nenahrazují integrační test
Dockeru na ARM64 ani ověření dostupnosti přes skutečný tailnet.

Použité principy: [Compose project names](https://docs.docker.com/compose/how-tos/project-name/),
[limity a konfigurace služeb](https://docs.docker.com/reference/compose-file/services/),
[oprávnění Docker démona](https://docs.docker.com/engine/security/).
