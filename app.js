const STORAGE_KEY = "assist.places.v1";
const GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search";
const WEATHER_URL = "https://api.open-meteo.com/v1/forecast";

const DEFAULT_PLACES = [
  {
    id: "tokyo",
    name: "Tokyo",
    admin: "Tokyo",
    country: "Japan",
    latitude: 35.6895,
    longitude: 139.6917,
    timezone: "Asia/Tokyo",
  },
  {
    id: "san-francisco",
    name: "San Francisco",
    admin: "California",
    country: "United States",
    latitude: 37.7749,
    longitude: -122.4194,
    timezone: "America/Los_Angeles",
  },
  {
    id: "london",
    name: "London",
    admin: "England",
    country: "United Kingdom",
    latitude: 51.5072,
    longitude: -0.1276,
    timezone: "Europe/London",
  },
];

const WMO = {
  0: "Clear",
  1: "Mostly clear",
  2: "Partly cloudy",
  3: "Overcast",
  45: "Fog",
  48: "Rime fog",
  51: "Light drizzle",
  53: "Drizzle",
  55: "Heavy drizzle",
  56: "Freezing drizzle",
  57: "Freezing drizzle",
  61: "Light rain",
  63: "Rain",
  65: "Heavy rain",
  66: "Freezing rain",
  67: "Freezing rain",
  71: "Light snow",
  73: "Snow",
  75: "Heavy snow",
  77: "Snow grains",
  80: "Rain showers",
  81: "Rain showers",
  82: "Heavy showers",
  85: "Snow showers",
  86: "Heavy snow showers",
  95: "Thunderstorm",
  96: "Thunderstorm",
  99: "Thunderstorm",
};

const form = document.getElementById("add-place-form");
const queryInput = document.getElementById("place-query");
const addBtn = document.getElementById("add-place-btn");
const suggestionsEl = document.getElementById("suggestions");
const statusEl = document.getElementById("status");
const placesEl = document.getElementById("places");

/** @type {Array<ReturnType<typeof normalizePlace>>} */
let places = loadPlaces();
/** @type {Map<string, {temperature:number, weatherCode:number, wind:number, humidity:number|null}>} */
const weatherById = new Map();
let suggestTimer = 0;
let activeSuggest = [];

function normalizePlace(raw) {
  return {
    id: String(raw.id),
    name: String(raw.name),
    admin: raw.admin ? String(raw.admin) : "",
    country: raw.country ? String(raw.country) : "",
    latitude: Number(raw.latitude),
    longitude: Number(raw.longitude),
    timezone: String(raw.timezone || "UTC"),
  };
}

function loadPlaces() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PLACES.map(normalizePlace);
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_PLACES.map(normalizePlace);
    }
    return parsed.map(normalizePlace).filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude));
  } catch {
    return DEFAULT_PLACES.map(normalizePlace);
  }
}

function savePlaces() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(places));
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("is-error", Boolean(isError));
}

function placeLabel(place) {
  return [place.admin, place.country].filter(Boolean).join(", ");
}

function formatTime(timezone) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
  }
}

function formatDate(timezone) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timezone,
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(new Date());
  }
}

function weatherLabel(code) {
  return WMO[code] || "Weather unavailable";
}

function renderPlaces() {
  if (places.length === 0) {
    placesEl.innerHTML = `
      <div class="empty">
        <strong>No places yet</strong>
        Add a city above to track its local time and weather.
      </div>
    `;
    return;
  }

  placesEl.innerHTML = places
    .map((place, index) => {
      const weather = weatherById.get(place.id);
      const region = placeLabel(place);
      const temp = weather ? `${Math.round(weather.temperature)}°` : "—";
      const condition = weather ? weatherLabel(weather.weatherCode) : "Loading weather…";
      const extras = weather
        ? [
            weather.humidity != null ? `${weather.humidity}% humidity` : null,
            Number.isFinite(weather.wind) ? `${Math.round(weather.wind)} km/h wind` : null,
          ]
            .filter(Boolean)
            .join(" · ")
        : "";

      return `
        <article class="place" style="animation-delay:${index * 40}ms" data-id="${escapeAttr(place.id)}">
          <div class="place__main">
            <h2 class="place__name">${escapeHtml(place.name)}</h2>
            ${region ? `<p class="place__region">${escapeHtml(region)}</p>` : ""}
            <p class="place__time" data-time>${escapeHtml(formatTime(place.timezone))}</p>
            <p class="place__date" data-date>${escapeHtml(formatDate(place.timezone))}</p>
          </div>
          <div class="place__weather">
            <div class="place__temp">${escapeHtml(temp)}</div>
            <div class="place__condition">${escapeHtml(condition)}</div>
            ${extras ? `<p class="place__extras">${escapeHtml(extras)}</p>` : ""}
          </div>
          <button type="button" class="place__remove" data-remove="${escapeAttr(place.id)}" aria-label="Remove ${escapeAttr(place.name)}">
            Remove
          </button>
        </article>
      `;
    })
    .join("");
}

function tickTimes() {
  for (const card of placesEl.querySelectorAll(".place")) {
    const id = card.getAttribute("data-id");
    const place = places.find((p) => p.id === id);
    if (!place) continue;
    const timeEl = card.querySelector("[data-time]");
    const dateEl = card.querySelector("[data-date]");
    if (timeEl) timeEl.textContent = formatTime(place.timezone);
    if (dateEl) dateEl.textContent = formatDate(place.timezone);
  }
}

async function fetchWeatherForPlaces() {
  if (places.length === 0) {
    weatherById.clear();
    renderPlaces();
    return;
  }

  const latitudes = places.map((p) => p.latitude).join(",");
  const longitudes = places.map((p) => p.longitude).join(",");
  const url =
    `${WEATHER_URL}?latitude=${latitudes}&longitude=${longitudes}` +
    `&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m` +
    `&timezone=auto`;

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Weather request failed (${res.status})`);
    const data = await res.json();
    const rows = Array.isArray(data) ? data : [data];

    rows.forEach((row, index) => {
      const place = places[index];
      if (!place || !row?.current) return;
      weatherById.set(place.id, {
        temperature: row.current.temperature_2m,
        weatherCode: row.current.weather_code,
        wind: row.current.wind_speed_10m,
        humidity: row.current.relative_humidity_2m ?? null,
      });
    });
    renderPlaces();
  } catch (error) {
    console.error(error);
    setStatus("Could not refresh weather. Times still update.", true);
    renderPlaces();
  }
}

async function searchPlaces(query) {
  const url = `${GEOCODE_URL}?name=${encodeURIComponent(query)}&count=6&language=en&format=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Search failed (${res.status})`);
  const data = await res.json();
  return Array.isArray(data.results) ? data.results : [];
}

function renderSuggestions(results) {
  activeSuggest = results;
  if (!results.length) {
    suggestionsEl.hidden = true;
    suggestionsEl.innerHTML = "";
    return;
  }

  suggestionsEl.hidden = false;
  suggestionsEl.innerHTML = results
    .map((item, index) => {
      const subtitle = [item.admin1, item.country].filter(Boolean).join(", ");
      return `
        <li role="option">
          <button type="button" data-suggest-index="${index}">
            ${escapeHtml(item.name)}
            ${subtitle ? `<span class="meta">${escapeHtml(subtitle)}</span>` : ""}
          </button>
        </li>
      `;
    })
    .join("");
}

function hideSuggestions() {
  suggestionsEl.hidden = true;
  suggestionsEl.innerHTML = "";
  activeSuggest = [];
}

function toPlace(result) {
  const id = [
    result.id ?? `${result.latitude},${result.longitude}`,
    result.name,
    result.country_code || "",
  ]
    .join("-")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-");

  return normalizePlace({
    id,
    name: result.name,
    admin: result.admin1 || "",
    country: result.country || "",
    latitude: result.latitude,
    longitude: result.longitude,
    timezone: result.timezone || "UTC",
  });
}

async function addPlaceFromResult(result) {
  const place = toPlace(result);
  if (places.some((p) => p.id === place.id || (p.name === place.name && p.country === place.country))) {
    setStatus(`${place.name} is already on your list.`);
    hideSuggestions();
    queryInput.value = "";
    return;
  }

  places = [place, ...places];
  savePlaces();
  hideSuggestions();
  queryInput.value = "";
  setStatus(`Added ${place.name}.`);
  renderPlaces();
  await fetchWeatherForPlaces();
}

function removePlace(id) {
  const removed = places.find((p) => p.id === id);
  places = places.filter((p) => p.id !== id);
  weatherById.delete(id);
  savePlaces();
  setStatus(removed ? `Removed ${removed.name}.` : "Place removed.");
  renderPlaces();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = queryInput.value.trim();
  if (!query) return;

  addBtn.disabled = true;
  setStatus("Searching…");

  try {
    const results = await searchPlaces(query);
    if (!results.length) {
      setStatus(`No matches for “${query}”.`, true);
      hideSuggestions();
      return;
    }
    if (results.length === 1) {
      await addPlaceFromResult(results[0]);
      return;
    }
    renderSuggestions(results);
    setStatus("Pick a place from the list.");
  } catch (error) {
    console.error(error);
    setStatus("Search failed. Check your connection and try again.", true);
  } finally {
    addBtn.disabled = false;
  }
});

queryInput.addEventListener("input", () => {
  const query = queryInput.value.trim();
  window.clearTimeout(suggestTimer);
  if (query.length < 2) {
    hideSuggestions();
    return;
  }

  suggestTimer = window.setTimeout(async () => {
    try {
      const results = await searchPlaces(query);
      renderSuggestions(results);
    } catch {
      // Keep typing quiet; submit still reports errors.
    }
  }, 280);
});

suggestionsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-suggest-index]");
  if (!button) return;
  const index = Number(button.getAttribute("data-suggest-index"));
  const result = activeSuggest[index];
  if (!result) return;
  addBtn.disabled = true;
  try {
    await addPlaceFromResult(result);
  } finally {
    addBtn.disabled = false;
  }
});

placesEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove]");
  if (!button) return;
  removePlace(button.getAttribute("data-remove"));
});

document.addEventListener("click", (event) => {
  if (!form.contains(event.target)) hideSuggestions();
});

renderPlaces();
fetchWeatherForPlaces();
window.setInterval(tickTimes, 1000);
window.setInterval(fetchWeatherForPlaces, 10 * 60 * 1000);
