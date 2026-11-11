# Casa Lagos

Casa Lagos is an independent planner concept for Lagos Life homes. It reflects the in-game above view, tile grid, two-floor controls, furniture footprints, and Game Naira price display. It does not control the game or sync plans to a Lagos Life account.

## Run locally

Requires Python 3.10 or newer; no third-party Python packages are needed.

```sh
cd /path/to/outputs
CASA_ADMIN_TOKEN='choose-a-long-private-key' python3 server.py
```

Open <http://127.0.0.1:8766>. The database is created at `data/casa_lagos.sqlite3`. Keep that file private; it contains Casa Lagos usernames, password hashes, sign-in timestamps and saved floor plans. The prototype does not store email addresses, passwords in plain text, IP addresses, or Lagos Life credentials. Sign-in events are removed after 90 days when the server starts and when the owner activity panel is refreshed.

Open <http://127.0.0.1:8766/admin.html> and enter the same `CASA_ADMIN_TOKEN` value to view the most recent Casa Lagos logins. If the token is not set when starting the server, owner activity is disabled. Use a different, unique password for every Casa Lagos account; never reuse a Lagos Life password.

## Deploy to Render

The repository includes a `render.yaml` Blueprint. In Render, create a Blueprint from this public GitHub repository and review the plan before confirming. This configuration uses an always-on Starter web service and a 1 GB persistent disk for SQLite. It sets the admin token as a generated secret. Render web services provide an HTTPS `onrender.com` address.

The app reads Render's `PORT`, binds to `0.0.0.0`, and sets Secure session cookies when served by Render. The persistent disk is required because Render filesystems are otherwise temporary. Render currently lists persistent disk storage at $0.25/GB/month; the Starter web-service compute price is currently $7/month, so the configured setup is about $7.25/month before any additional usage or taxes. Check the dashboard's current estimate before creating the service.

Before inviting public users, add account recovery, login rate limits, a privacy notice/terms, and review Vatar's developer integration requirements. Casa Lagos uses its own accounts and does not collect Lagos Life credentials or control the game.

## Game references

- In-game home and furniture views checked on 11 Nov 2026.
- Current sample prices displayed in the planner: Wall Calendar ₦300, Bucket & Bowl ₦400, Velvet Sofa ₦10,200, Ankara Rug ₦2,600, Adire Wall Art ₦5,400, Royal Gold Sofa ₦55,000, Royal Persian Carpet ₦4.5m and Gold Lion Statue ₦50m. The catalogue can change; the Buy catalogue in Lagos Life is authoritative. Smaller starter-item prices for Plastic Chair, Fela Poster and Potted Plant are public-guide references and are marked for re-check in the planner.
- Home rent references and how-to steps: [Lagos Life official home guide](https://lagoslife.app/wiki/guide/life-moving-renting-and-buying-homes-houses-app), [official build and home guide](https://lagoslife.app/wiki/how-to), and [Lagos Life terms](https://lagoslife.app/terms).
- Player build inspiration: the three TikTok tours linked in the Build stories section.

Lagos Life, its game materials and marks belong to their respective owners. This is an unofficial fan concept; no developer partnership or API access is in place.
