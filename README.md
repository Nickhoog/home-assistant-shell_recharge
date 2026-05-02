# 🟡⚠️ WORK IN PROGRESS - NOT WORKING YET ⚠️🟡

> ## 🚧 This integration is currently under active development
> - Expect errors
> - Features are incomplete
> - API (Shell EV) is unstable in sandbox
> - Breaking changes may happen at any time

---

# Shell Recharge Custom Integration

⚡ Monitor public Shell Recharge EV chargers in Home Assistant using the official Shell EV API.

---

## 🔥 Current Status

- ✅ Config flow works
- ✅ API authentication implemented
- ⚠️ Sandbox API unstable (500 errors)
- 🚧 Sensors & multi-location still in development

---

## 🚀 Quick Start

1. Install via HACS
2. Add integration
3. Enter:

```
client_id
client_secret
latitude
longitude
limit
```

---

## 🧪 Sandbox Notes

Shell sandbox is… let’s say… “temperamental”:

- Random **500 / 503 errors**
- Sometimes returns **no data**
- Not representative of production

👉 If it fails: it’s probably NOT your fault

---

## 📍 Features (WIP)

- Nearby charger lookup
- EVSE status monitoring
- Multi-location support (coming)

---

## ⚙️ API Setup

Get credentials via:
👉 https://developer.shell.com

Required product:
```
B2B EV Locations
```

---

## 🧠 How it works

Uses:
```
/ev/v1/locations/nearby
```

---

## 🚧 Roadmap

- [ ] Stable sandbox handling
- [ ] Production support toggle
- [ ] Sensors per charger
- [ ] Better error handling
- [ ] Notifications

---

## ⚠️ Disclaimer

Not affiliated with Shell. Use at your own risk.
