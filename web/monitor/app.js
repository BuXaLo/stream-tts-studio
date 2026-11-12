(() => {
const $ = id => document.getElementById(id);
const generations = [], logs = [], seenEvents = new Set();
const counts = { info: 0, warning: 0, error: 0 };
let activeFilter = "all";
let socket = null;
let launcherMode = new URLSearchParams(location.search).has("launcher");
let backendActive = false;
let backendConnected = false;
let shutdownRequested = false;
let startupOffset = 0;
let startupDecoder = new TextDecoder("utf-8");
let startupEncoder = new TextEncoder();
let startupBuffer = "";
let startupBufferOffset = 0;
let startupLastEvent = null;
let startupSuppressCosyVoiceContinuation = false;

const timeText = value => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value || "—") : date.toLocaleTimeString("ru-RU");
};
const duration = value => Number.isFinite(Number(value)) ? Number(value).toFixed(2) + " с" : "—";

function renderGenerations() {
    const body = $("generationRows");
    body.replaceChildren();
    $("generationCount").textContent = generations.length + " событий";
    if (!generations.length) {
        const tr = document.createElement("tr"), td = document.createElement("td");
        td.colSpan = 6;
        td.className = "empty";
        td.textContent = "Ожидание запросов на озвучку…";
        tr.append(td);
        body.append(tr);
        return;
    }
    generations.slice(0, 100).forEach(item => {
        const tr = document.createElement("tr");
        const values = [timeText(item.timestamp), item.text || "", item.character || item.char_id || "—",
            duration(item.synthesis_seconds), duration(item.audio_duration),
            item.status === "complete" ? "Готово" : item.status === "started" ? "В работе" : "Ошибка"];
        values.forEach((value, index) => {
            const td = document.createElement("td");
            td.textContent = value;
            if (index === 0) td.className = "time";
            if (index === 1) td.className = "message";
            if (index === 3 || index === 4) td.className = "metric";
            if (index === 5) {
                const pill = document.createElement("span");
                pill.className = "pill " + (item.status === "started" ? "running" : item.status === "error" ? "failed" : "");
                pill.textContent = value;
                td.replaceChildren(pill);
            }
            tr.append(td);
        });
        body.append(tr);
    });
}

function renderLogs() {
    const root = $("logRows");
    root.replaceChildren();
    const visible = logs.filter(item => activeFilter === "all" || item.level === activeFilter);
    if (!visible.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Нет событий для выбранного фильтра";
        root.append(empty);
        return;
    }
    visible.slice(0, 250).forEach(item => {
        const row = document.createElement("div");
        row.className = "log-row";
        const time = document.createElement("span");
        time.className = "log-time";
        time.textContent = timeText(item.timestamp);
        const level = document.createElement("span");
        level.className = "log-level " + item.level;
        level.textContent = (item.level || "info").toUpperCase();
        const message = document.createElement("span");
        message.className = "log-message";
        const source = document.createElement("span");
        source.className = "log-source";
        source.textContent = item.logger || "studio";
        message.append(source, document.createTextNode(item.message || ""));
        row.append(time, level, message);
        root.append(row);
    });
}

function handleEvent(event) {
    if (event.event_id && seenEvents.has(event.event_id)) return;
    if (event.event_id) {
        seenEvents.add(event.event_id);
        if (seenEvents.size > 1500) seenEvents.delete(seenEvents.values().next().value);
    }
    if (event.type === "generation") {
        const index = generations.findIndex(item => item.request_id === event.request_id);
        if (index >= 0) {
            event.timestamp = generations[index].timestamp;
            generations[index] = event;
        } else {
            generations.unshift(event);
        }
        while (generations.length > 200) generations.pop();
        renderGenerations();
    }
    if (event.type === "log") {
        logs.unshift(event);
        while (logs.length > 500) logs.pop();
        const level = event.level === "warn" ? "warning" : event.level;
        if (counts[level] !== undefined) {
            counts[level]++;
            $(level === "warning" ? "warningCount" : level + "Count").textContent = counts[level];
        }
        renderLogs();
    }
    if (event.type === "shutdown") {
        backendActive = false;
        shutdownRequested = true;
        $("shutdownButton").disabled = true;
        $("shutdownButton").textContent = "Выключение…";
        $("connectionText").textContent = "Завершение работы";
    }
}

function setLauncherButton(status) {
    const button = $("shutdownButton");
    if (status === "ready") {
        button.disabled = false;
        button.textContent = "Выключить студию";
        button.className = "button danger";
    } else if (status === "stopped" || status === "error") {
        button.disabled = false;
        button.textContent = "Запустить студию";
        button.className = "button secondary";
        shutdownRequested = false;
    } else {
        button.disabled = true;
        button.textContent = status === "stopping" ? "Выключение…" : "Запуск студии…";
    }
}

function connect(backendUrl) {
    const parsed = new URL(backendUrl);
    const scheme = parsed.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(scheme + "://" + parsed.host + "/ws/monitor");
    socket.onopen = () => {
        backendConnected = true;
        $("connectionText").textContent = "Подключено";
        $("connectionDot").parentElement.className = "status connected";
        if (!shutdownRequested) setLauncherButton("ready");
    };
    socket.onmessage = message => {
        try {
            const event = JSON.parse(message.data);
            if (launcherMode && event.type === "log") return;
            handleEvent(event);
        } catch (_) {}
    };
    socket.onclose = event => {
        backendConnected = false;
        socket = null;
        $("connectionText").textContent = "Нет соединения" +
            (event.code && event.code !== 1000 ? " (код " + event.code + (event.reason ? ": " + event.reason : "") + ")" : "");
        $("connectionDot").parentElement.className = "status disconnected";
        if (!launcherMode || backendActive) setTimeout(() => connect(backendUrl), 2000);
    };
    socket.onerror = () => {
        $("connectionText").textContent = "Ошибка WebSocket";
        socket.close();
    };
}

function startupLevel(message) {
    if (/Traceback|Error|Exception|CRITICAL/i.test(message)) return "error";
    if (/Warning|^WARNING\b/i.test(message)) return "warning";
    return "info";
}

function isCosyVoiceAmpFutureWarning(message) {
    return /cosyvoice[\\/]+cli[\\/]+model\.py:\d+/i.test(message) &&
        /FutureWarning/i.test(message) &&
        /torch\.cuda\.amp\.autocast/i.test(message);
}

function addStartupLines(content) {
    startupBuffer += content;
    let newlineIndex;
    while ((newlineIndex = startupBuffer.indexOf("\n")) !== -1) {
        const rawWithEnding = startupBuffer.slice(0, newlineIndex + 1);
        startupBuffer = startupBuffer.slice(newlineIndex + 1);
        const rawLine = rawWithEnding.replace(/\r?\n$/, "");
        if (startupSuppressCosyVoiceContinuation) {
            if (/^[ \t]/.test(rawLine)) {
                startupBufferOffset += startupEncoder.encode(rawWithEnding).length;
                continue;
            }
            startupSuppressCosyVoiceContinuation = false;
        }
        if (isCosyVoiceAmpFutureWarning(rawLine)) {
            startupSuppressCosyVoiceContinuation = true;
            startupBufferOffset += startupEncoder.encode(rawWithEnding).length;
            continue;
        }
        if (!rawLine.trim()) {
            startupCosyVoiceSourceCandidate = null;
            startupBufferOffset += startupEncoder.encode(rawWithEnding).length;
            continue;
        }
        if (/^[ \t]/.test(rawLine) && startupLastEvent) {
            startupCosyVoiceSourceCandidate = null;
            const previousLevel = startupLastEvent.level;
            startupLastEvent.message += "\n" + rawLine;

            if (nextLevel !== previousLevel) {
                counts[previousLevel]--;
                counts[nextLevel]++;
                $(previousLevel === "warning" ? "warningCount" : previousLevel + "Count").textContent = counts[previousLevel];
                $(nextLevel === "warning" ? "warningCount" : nextLevel + "Count").textContent = counts[nextLevel];
                startupLastEvent.level = nextLevel;
            }
            renderLogs();
            startupBufferOffset += startupEncoder.encode(rawWithEnding).length;
            continue;
        }
        const lineOffset = startupBufferOffset;
        const match = rawLine.match(/^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)\s+(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL)\s+(.*)$/);
        const event = {
            event_id: "startup:" + lineOffset,
            type: "log",

            logger: "startup",
            timestamp: match ? match[1].replace(" ", "T").replace(",", ".") : new Date().toISOString(),

        };
        handleEvent(event);
        startupBufferOffset += startupEncoder.encode(rawWithEnding).length;
    }
}

async function pollLauncher() {
    try {
        const [statusResponse, logResponse] = await Promise.all([
            fetch("/launcher-status", { cache: "no-store" }),
            fetch("/startup-log?offset=" + startupOffset, { cache: "no-store" })
        ]);
        if (!statusResponse.ok || !logResponse.ok) throw new Error("Не удалось получить состояние запуска");
        const status = await statusResponse.json();
        const offsetHeader = logResponse.headers.get("X-Log-Offset");
        const nextOffset = offsetHeader === null ? NaN : Number(offsetHeader);
        if (Number.isFinite(nextOffset) && nextOffset < startupOffset) {
            startupDecoder = new TextDecoder("utf-8");
            startupBuffer = "";
            startupBufferOffset = 0;
            startupLastEvent = null;
        }
        addStartupLines(startupDecoder.decode(await logResponse.arrayBuffer(), { stream: true }));
        if (Number.isFinite(nextOffset)) startupOffset = nextOffset;

        if (status.close_monitor) {
            window.close();
        }

        if (status.status === "ready") {
            backendActive = true;
            $("connectionText").textContent = backendConnected ? "Подключено" : "Backend запущен, подключение…";
            if (!shutdownRequested) setLauncherButton("ready");
            if (!socket) connect(status.backend_url);
        } else if (status.status === "error") {
            backendActive = false;
            setLauncherButton("error");
            $("connectionText").textContent = status.detail || "Ошибка запуска backend";
            $("connectionDot").parentElement.className = "status disconnected";
        } else if (status.status === "stopped") {
            backendActive = false;
            setLauncherButton("stopped");
            $("connectionText").textContent = "Студия остановлена";
            $("connectionDot").parentElement.className = "status disconnected";
        } else {
            backendActive = false;
            setLauncherButton("starting");
            $("connectionText").textContent = "Запуск backend…";
        }
    } catch (error) {
        $("connectionText").textContent = "Нет связи с загрузчиком";
    }
    if (launcherMode) setTimeout(pollLauncher, 700);
}

document.querySelectorAll("[data-filter]").forEach(button => button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    document.querySelectorAll(".filter").forEach(item => item.classList.toggle("active", item === button));
    renderLogs();
    document.querySelector(".logs-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}));

$("shutdownButton").addEventListener("click", async () => {
    if (launcherMode && !backendActive) {
        $("shutdownButton").disabled = true;
        $("shutdownButton").textContent = "Запуск студии…";
        try {
            const response = await fetch("/launcher-start", { method: "POST" });
            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                throw new Error(detail.detail || "HTTP " + response.status);
            }
            shutdownRequested = false;
            $("connectionText").textContent = "Запуск backend…";
        } catch (error) {
            alert("Не удалось запустить студию: " + error.message);
            setLauncherButton("stopped");
        }
        return;
    }
    if (!confirm("Завершить работу студии? Текущая генерация будет завершена перед остановкой.")) return;
    $("shutdownButton").disabled = true;
    $("shutdownButton").textContent = "Выключение…";
    shutdownRequested = true;
    try {
        const shutdownUrl = launcherMode ? "/launcher-stop" : location.origin + "/api/monitor/shutdown";
        const response = await fetch(shutdownUrl, { method: "POST" });
        if (!response.ok) throw new Error("HTTP " + response.status);
        $("connectionText").textContent = "Студия выключается";
    } catch (error) {
        alert("Не удалось выключить студию: " + error.message);
        shutdownRequested = false;
        setLauncherButton("ready");
    }
});

const dashboardButton = $("dashboardButton");
if (dashboardButton) {
    dashboardButton.addEventListener("click", async () => {
        if (!launcherMode) {
            window.open(location.origin + "/", "_blank", "noopener");
            return;
        }
        dashboardButton.disabled = true;
        try {
            const response = await fetch("/open-dashboard", { method: "POST" });
            if (!response.ok) throw new Error("Не удалось открыть Dashboard");
        } catch (error) {
            alert(error.message);
        } finally {
            dashboardButton.disabled = false;
        }
    });
}

if (launcherMode) {
    setLauncherButton("starting");
    pollLauncher();
} else {
    connect(location.origin);
}
setInterval(() => $("clock").textContent = new Date().toLocaleString("ru-RU"), 1000);
})();
