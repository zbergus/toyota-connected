# Toyota Connected Services API Contracts

This directory defines the canonical API contracts and golden test fixtures for Toyota Connected Services across North America and Europe.

---

## 1. Architecture & Protocol Matrix

Toyota utilizes two telematics architectures in North America depending on the vehicle generation:

| Vehicle Generation | Example Models | Telematics Gateway | Protocol | Status Fixtures |
| :--- | :--- | :--- | :--- | :--- |
| **MM24 / MM25** | 2025+ bZ4X, 2024+ Grand Highlander, Land Cruiser, Tacoma, Lexus TX | AWS AppSync GraphQL (`/graphql`) | GraphQL Queries, Mutations & WebSocket Subscriptions | `telemetry_bev_metric.json`<br>`telemetry_hybrid_ice.json`<br>`telemetry_bev_imperial.json` |
| **21MM** | 2023–2024 bZ4X, 2022–2024 Tundra, RAV4 Prime, Sequoia, Lexus NX | Toyota OneAPI REST (`api.toyota.com`) | JSON REST APIs over HTTPS | `na_electric_status_bev.json`<br>`na_telemetry_bev.json`<br>`na_remote_status.json` |
| **Europe (TME)** | bZ4X, Yaris Cross, RAV4, Corolla (EU spec) | TME CTPA OneAPI (`ctpa-oneapi.tme.toyota-europe.com`) | JSON REST APIs over HTTPS | `eu_electric_status.json`<br>`eu_vehicle_status.json` |

---

## 2. North America 21MM REST Contracts

Used for 2023–2024 bZ4X and other 21MM headunit vehicles.

### Common Required Headers
```http
X-ApiKey: {brand_api_key}
User-Agent: {brand_user_agent}
Authorization: Bearer {id_token}
guid: {user_guid}
vin: {vehicle_vin}
```

### Endpoints
1. **Electric Vehicle Status**: `GET /v2/electric/status`
   - **Contract Fixture**: [`contracts/fixtures/na_electric_status_bev.json`](fixtures/na_electric_status_bev.json)
   - **Key Fields**:
     - `chargeRemainingAmount`: Battery state of charge (percentage 0–100)
     - `evDistance` / `evTravelableDistance`: EV range in km with AC off
     - `evDistanceAC`: EV range in km with AC on
     - `plugStatus`: `12` = unplugged, `40`/`56` = actively charging
     - `connectorStatus`: `1` = plugged, `2` = unplugged
     - `remainingChargeTime`: Remaining charge minutes (`65535` = sentinel for not charging / idle)
     - `remoteHvacInfo.settingTemperature`: Target climate temperature (°C)
     - `remoteHvacInfo.remoteHvacMode`: `0` = off, `1` = active

2. **Telemetry & Tire Pressure**: `GET /v2/telemetry`
   - **Contract Fixture**: [`contracts/fixtures/na_telemetry_bev.json`](fixtures/na_telemetry_bev.json)
   - **Key Fields**:
     - `odometer.value`: Current odometer reading (and `.unit`)
     - `flTirePressure.value`, `frTirePressure.value`, `rlTirePressure.value`, `rrTirePressure.value`: Tire pressure in PSI or kPa

3. **Doors, Windows & Openings**: `GET /v1/global/remote/status`
   - **Contract Fixture**: [`contracts/fixtures/na_remote_status.json`](fixtures/na_remote_status.json)
   - **Key Fields**:
     - `vehicleStatus`: Array of categories (`Driver Side`, `Passenger Side`, `Other`)
     - Sections contain `"Close"` / `"Open"` and `"Lock"` / `"Unlock"`
     - `latitude` / `longitude`: Last parked GPS position

4. **Remote Commands**: `POST /v1/global/remote/command`
   - **Payload**:
     ```json
     {
       "command": "door-lock", // "door-unlock", "hazard-on", "hazard-off", "ac-start", "ac-stop"
       "vin": "{vin}"
     }
     ```

---

## 3. MM24 / MM25 AppSync GraphQL Contracts

Used for 2025+ models with the newer headunit.

- **GraphQL Schema**: [`contracts/schemas/telemetry.graphql`](schemas/telemetry.graphql)
- **Golden Fixtures**:
  - BEV Metric (bZ4X): [`contracts/fixtures/telemetry_bev_metric.json`](fixtures/telemetry_bev_metric.json)
  - BEV Imperial: [`contracts/fixtures/telemetry_bev_imperial.json`](fixtures/telemetry_bev_imperial.json)
  - Hybrid / ICE: [`contracts/fixtures/telemetry_hybrid_ice.json`](fixtures/telemetry_hybrid_ice.json)

---

## 4. Contract Verification

These golden fixtures ensure that vehicle telemetry parsers accurately decode raw gateway payloads into typed models without schema regressions.
