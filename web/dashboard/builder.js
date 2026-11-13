// ==================== ИНТЕРАКТИВНЫЙ C# КОНСТРУКТОР ДЛЯ STREAMER.BOT ====================

const defaultPhrases = {
    follow: [
        "Привет, {user}! Рады видеть тебя на трансляции, добро пожаловать в нашу команду.",
        "О, новый зритель! {user}, привет и добро пожаловать на стрим.",
        "Привет-привет, {user}! Спасибо за подписку, устраивайся поудобнее.",
        "{user}, отличный выбор! Присоединяйся к нашему чату."
    ],
    raid: [
        "Приветствуем рейд от {streamer}! К нам пришла отличная компания — {viewers_phrase}. Добро пожаловать!",
        "Ого, рейд от {streamer}! Целых {viewers_phrase}! Рады видеть каждого из вас на нашей трансляции.",
        "Привет, {streamer}! Спасибо за рейд и заглянувших {viewers_phrase}. Располагайтесь и приятного просмотра!"
    ]
};

function getServerSpeakUrl() {
    const hostInput = document.getElementById('cfg-host');
    const portInput = document.getElementById('cfg-port');

    let host = hostInput ? hostInput.value.trim() : '127.0.0.1';
    let port = portInput ? parseInt(portInput.value, 10) || 8765 : 8765;

    if (host === '0.0.0.0' || !host) {
        host = '127.0.0.1';
    }

    return `http://${host}:${port}/speak`;
}

function updateGeneratorCharacterDropdown() {
    const sel = document.getElementById('gen-char-select');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">(По умолчанию — активный персонаж)</option>';

    if (typeof currentPresets !== 'undefined' && currentPresets) {
        Object.keys(currentPresets).forEach(id => {
            const name = currentPresets[id].name || id;
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = `${name} (${id})`;
            if (id === currentVal) opt.selected = true;
            sel.appendChild(opt);
        });
    }
}

function initScriptGenerator() {
    const eventTypeSel = document.getElementById('gen-event-type');
    const charSelect = document.getElementById('gen-char-select');
    const optionsTts = document.getElementById('gen-options-tts');
    const optionsPhrases = document.getElementById('gen-options-phrases');
    const optionsDonate = document.getElementById('gen-options-donate');
    const maxLenInp = document.getElementById('gen-max-len');
    const limitActionSel = document.getElementById('gen-limit-action');
    const limitTextInp = document.getElementById('gen-limit-text');
    const phraseModeSel = document.getElementById('gen-phrase-mode');
    const phrasesContainer = document.getElementById('gen-phrases-container');
    const btnAddPhrase = document.getElementById('btn-add-phrase');
    const varsHint = document.getElementById('gen-vars-hint');
    const donateNoMsgInp = document.getElementById('gen-donate-nomessage');
    const donateWithMsgInp = document.getElementById('gen-donate-withmessage');
    const codeBox = document.getElementById('code-generated');
    const btnCopyGen = document.getElementById('btn-copy-generated');

    const cfgHostInp = document.getElementById('cfg-host');
    const cfgPortInp = document.getElementById('cfg-port');

    if (!eventTypeSel) return;

    if (window.StudioUI && typeof window.StudioUI.syncAllSegmentedControls === 'function') {
        window.StudioUI.syncAllSegmentedControls();
    }

    function renderPhraseInputs(type, mode) {
        if (!phrasesContainer) return;
        phrasesContainer.replaceChildren();
        const phrases = defaultPhrases[type] || ["Привет, {user}!"];

        if (mode === 'single') {
            if (btnAddPhrase) btnAddPhrase.classList.add('hidden');
            const div = document.createElement('div');
            div.className = 'phrase-row-item';
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'phrase-input';
            inp.value = phrases[0];
            inp.addEventListener('input', updateGeneratedCode);
            div.appendChild(inp);
            phrasesContainer.appendChild(div);
        } else {
            if (btnAddPhrase) btnAddPhrase.classList.remove('hidden');
            phrases.forEach(p => addPhraseRow(p));
        }
    }

    function addPhraseRow(val = "") {
        if (!phrasesContainer) return;
        const div = document.createElement('div');
        div.className = 'phrase-row-item';

        const inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'phrase-input';
        inp.value = val;
        inp.addEventListener('input', updateGeneratedCode);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'btn-remove-phrase';
        removeBtn.title = 'Удалить';
        removeBtn.textContent = '✖';
        removeBtn.addEventListener('click', () => {
            if (phrasesContainer.children.length > 1) {
                div.remove();
                updateGeneratedCode();
            } else {
                alert('Нужен хотя бы один вариант фразы!');
            }
        });

        div.append(inp, removeBtn);
        phrasesContainer.appendChild(div);
    }

    if (btnAddPhrase) {
        btnAddPhrase.addEventListener('click', () => {
            addPhraseRow("Еще один вариант фразы для {user}!");
            updateGeneratedCode();
        });
    }

    function updateFormVisibility() {
        const type = eventTypeSel.value;
        if (optionsTts) optionsTts.classList.add('hidden');
        if (optionsPhrases) optionsPhrases.classList.add('hidden');
        if (optionsDonate) optionsDonate.classList.add('hidden');

        if (type === 'tts') {
            if (optionsTts) optionsTts.classList.remove('hidden');
        } else if (type === 'donate') {
            if (optionsDonate) optionsDonate.classList.remove('hidden');
        } else {
            if (optionsPhrases) optionsPhrases.classList.remove('hidden');
            if (varsHint) {
                if (type === 'follow') {
                    varsHint.innerHTML = '📌 Переменные: <code>{user}</code> — ник фолловера.';
                } else if (type === 'raid') {
                    varsHint.innerHTML = '📌 Переменные: <code>{streamer}</code> — ник стримера; <code>{viewers_phrase}</code> — количество зрителей со словом (напр. "15 человек", цифру сервер озвучит сам).';
                }
            }
            renderPhraseInputs(type, phraseModeSel ? phraseModeSel.value : 'random');
        }
        updateGeneratedCode();
    }

    function getCommonHelpers(includeMoney, includeHuman, serverUrls) {
        let res = "";
        res += '\n    // Первый адрес — локальная студия. Если Streamer.bot на другом ПК, замените 192.168.1.111 на IP компьютера со Stream TTS Studio.\n';
        res += '    private static readonly string[] ServerUrls = { "' + serverUrls.primary + '", "' + serverUrls.secondary + '" };\n';
        res += '    private const int CacheSeconds = 30;\n';
        res += '    private static readonly HttpClient probeClient = new HttpClient { Timeout = TimeSpan.FromSeconds(1.5) };\n';
        res += '\n    private byte[] RequestWav(string json)\n    {\n        for (int attempt = 0; attempt < 2; attempt++)\n        {\n            string baseUrl = ResolveServer(attempt > 0);\n            if (baseUrl == null) return null;\n            try\n            {\n                var content = new StringContent(json, Encoding.UTF8, "application/json");\n                var response = client.PostAsync(baseUrl + "/speak", content).GetAwaiter().GetResult();\n                if (!response.IsSuccessStatusCode)\n                {\n                    CPH.LogError("TTS ответил кодом " + (int)response.StatusCode + " (" + baseUrl + ")");\n                    return null; // сервер жив, но отказал: не перебираем\n                }\n                byte[] wav = response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();\n                return wav.Length < 1000 ? null : wav;\n            }\n            catch (HttpRequestException ex) { CPH.LogWarn("TTS недоступен (" + baseUrl + "): " + ex.Message); }\n            catch (TaskCanceledException ex) { CPH.LogWarn("TTS таймаут (" + baseUrl + "): " + ex.Message); }\n        }\n        return null;\n    }\n';
        res += '\n    private string ResolveServer(bool force)\n    {\n        if (!force)\n        {\n            string cached = CPH.GetGlobalVar<string>("tts_base_url", false);\n            long ts = CPH.GetGlobalVar<long>("tts_base_url_ts", false);\n            if (!string.IsNullOrEmpty(cached) && Array.IndexOf(ServerUrls, cached) >= 0 && (DateTime.UtcNow.Ticks - ts) < TimeSpan.FromSeconds(CacheSeconds).Ticks)\n                return cached;\n        }\n\n        foreach (string baseUrl in ServerUrls)\n        {\n            try\n            {\n                var response = probeClient.GetAsync(baseUrl + "/api/system_config").GetAwaiter().GetResult();\n                if (response.IsSuccessStatusCode)\n                {\n                    CPH.SetGlobalVar("tts_base_url", baseUrl, false);\n                    CPH.SetGlobalVar("tts_base_url_ts", DateTime.UtcNow.Ticks, false);\n                    return baseUrl;\n                }\n            }\n            catch { }\n        }\n        return null;\n    }\n';

        res += "\n    private static string EscapeJson(string s) => s.Replace(\"\\\\\", \"\\\\\\\\\").Replace(\"\\\"\", \"\\\\\\\"\").Replace(\"\\r\", \"\\\\r\").Replace(\"\\n\", \"\\\\n\");\n";

        res += "\n    private static string CleanForTTS(string s)\n";
        res += "    {\n";
    res += "        s = Regex.Replace(s, @\"\\p{Cs}|\\p{So}|\\p{Sk}|\\p{Sm}|[\\u200D\\uFE0F\\u20E3]\", \"\");\n";
        res += "        s = Regex.Replace(s, @\"[\\*\\\"`\\_\\#\\[\\]\\(\\)<>~]\", \"\");\n";
        res += "        return Regex.Replace(s, @\"\\s+\", \" \").Trim();\n";
        res += "    }\n";

        if (includeHuman) {
            res += "\n    private static string GetHumanDeclension(int n)\n";
            res += "    {\n";
            res += "        int rem100 = Math.Abs(n) % 100;\n";
            res += "        int rem10 = rem100 % 10;\n";
            res += "        if (rem100 >= 11 && rem100 <= 19) return \"человек\";\n";
            res += "        if (rem10 >= 2 && rem10 <= 4) return \"человека\";\n";
            res += "        return \"человек\";\n";
            res += "    }\n";
        }

        if (includeMoney) {
            res += "\n    private static string FormatMoneyWithDeclension(int amount, string currency) => amount.ToString() + \" \" + GetCurrencyDeclension(amount, currency);\n";
            res += "\n    private static string GetCurrencyDeclension(int n, string currency)\n";
            res += "    {\n";
            res += "        int rem100 = Math.Abs(n) % 100;\n";
            res += "        int rem10 = rem100 % 10;\n";
            res += "        switch (currency)\n";
            res += "        {\n";
            res += "            case \"USD\": return (rem100 >= 11 && rem100 <= 19) ? \"долларов\" : (rem10 == 1 ? \"доллар\" : (rem10 >= 2 && rem10 <= 4 ? \"доллара\" : \"долларов\"));\n";
            res += "            case \"EUR\": return \"евро\";\n";
            res += "            case \"KZT\": return \"тенге\";\n";
            res += "            case \"BYN\": return (rem100 >= 11 && rem100 <= 19) ? \"белорусских рублей\" : (rem10 == 1 ? \"белорусский рубль\" : (rem10 >= 2 && rem10 <= 4 ? \"белорусских рубля\" : \"белорусских рублей\"));\n";
            res += "            case \"RUB\":\n";
            res += "            default: return (rem100 >= 11 && rem100 <= 19) ? \"рублей\" : (rem10 == 1 ? \"рубль\" : (rem10 >= 2 && rem10 <= 4 ? \"рубля\" : \"рублей\"));\n";
            res += "        }\n";
            res += "    }\n";
        }

        return res;
    }

    function updateGeneratedCode() {
        if (!codeBox) return;

        const type = eventTypeSel ? eventTypeSel.value : 'tts';
        const charId = charSelect ? charSelect.value.trim() : "";
        const charArg = charId ? `,\\"character\\":\\"${charId}\\"` : "";
        const serverUrl = getServerSpeakUrl();
        const serverPort = (serverUrl.match(/:(\d+)\/speak$/) || [])[1] || '8765';
        const primaryServerUrl = serverUrl.replace(/\/speak$/, '');
        const secondaryServerUrl = 'http://192.168.1.111:' + serverPort;
        const serverUrls = { primary: primaryServerUrl, secondary: secondaryServerUrl };
        let code = "";

        if (type === 'tts') {
            const maxLen = maxLenInp ? (parseInt(maxLenInp.value, 10) || 300) : 300;
            const action = limitActionSel ? limitActionSel.value : 'chat';
            const limitText = limitTextInp ? limitTextInp.value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') : 'Твое сообщение слишком длинное!';

            code = `using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Net.Http;
using System.Threading.Tasks;

public class CPHInline
{
    private static readonly HttpClient client = new HttpClient();
    private static readonly string OutputDirectory = Path.Combine(Path.GetTempPath(), "TTS_Stream_Buffer");
    private const int MaxLength = ${maxLen};
    private static int fileIndex = 0;

    public bool Execute()
    {
        try
        {
            CPH.LogInfo("=== TTS EVENT: START ===");

            string userName = "Зритель";
            if (CPH.TryGetArg("user", out string userArg) && !string.IsNullOrWhiteSpace(userArg)) userName = userArg;
            else if (CPH.TryGetArg("userName", out string uNameArg) && !string.IsNullOrWhiteSpace(uNameArg)) userName = uNameArg;

            string text;
            if (!CPH.TryGetArg("rawInput", out text) || string.IsNullOrWhiteSpace(text))
            {
                if (!CPH.TryGetArg("prompt", out text) || string.IsNullOrWhiteSpace(text))
                {
                    if (!CPH.TryGetArg("message", out text) || string.IsNullOrWhiteSpace(text))
                    {
                        CPH.SendMessage($"@{userName}, текст сообщения для озвучки не может быть пустым!");
                        return false;
                    }
                }
            }

            text = text.Trim();
            if (text.Length > MaxLength)
            {`;
            if (action === 'chat') {
                code += `
                CPH.SendMessage($"@{userName}, твое сообщение слишком длинное ({text.Length} симв.)! Лимит — {MaxLength}.");
                return false;`;
            } else {
                code += `
                text = "${limitText}";`;
            }
            code += `
            }

            string cleanText = CleanForTTS(text);
            if (string.IsNullOrWhiteSpace(cleanText)) return false;

            Directory.CreateDirectory(OutputDirectory);
            string json = "{\\"text\\":\\"" + EscapeJson(cleanText) + "\\"${charArg}}";

            byte[] wav = RequestWav(json);
            if (wav == null)
            {
                CPH.SendMessage($"@{userName}, TTS-сервер сейчас недоступен.");
                return false;
            }

            fileIndex = (fileIndex % 3) + 1;
            string outputFile = Path.Combine(OutputDirectory, "tts_" + fileIndex + ".wav");
            File.WriteAllBytes(outputFile, wav);

            CPH.PlaySound(outputFile, 1.0f, true);
            CPH.LogInfo("=== TTS EVENT: SUCCESS ===");
            return true;
        }
        catch (Exception ex)
        {
            CPH.LogError("TTS EXCEPTION: " + ex.ToString());
            return false;
        }
    }
` + getCommonHelpers(false, false, serverUrls) + `
}`;
        } else if (type === 'donate') {
            const tplNoMsg = (donateNoMsgInp ? donateNoMsgInp.value : "Спасибо, {user}, за поддержку в размере {amount}!").replace(/\\/g, '\\\\').replace(/"/g, '\\"');
            const tplWithMsg = (donateWithMsgInp ? donateWithMsgInp.value : "{user} прислал {amount} с сообщением: {message}").replace(/\\/g, '\\\\').replace(/"/g, '\\"');

            code = `using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Net.Http;
using System.Threading.Tasks;

public class CPHInline
{
    private static readonly HttpClient client = new HttpClient();
    private static readonly string OutputDirectory = Path.Combine(Path.GetTempPath(), "TTS_Stream_Buffer");
    private static int alertFileIndex = 0;

    public bool Execute()
    {
        try
        {
            CPH.LogInfo("=== EVENT: DONATION ===");

            string donorName = "Добрый человек";
            if (CPH.TryGetArg("user", out string u) && !string.IsNullOrWhiteSpace(u)) donorName = u;
            else if (CPH.TryGetArg("donorName", out string dn) && !string.IsNullOrWhiteSpace(dn)) donorName = dn;
            else if (CPH.TryGetArg("userName", out string un) && !string.IsNullOrWhiteSpace(un)) donorName = un;

            int amount = 100;
            if (CPH.TryGetArg("amount", out int amtInt)) amount = amtInt;
            else if (CPH.TryGetArg("amount", out double amtDbl)) amount = (int)Math.Round(amtDbl);

            string currency = "RUB";
            if (CPH.TryGetArg("currency", out string cur) && !string.IsNullOrWhiteSpace(cur)) currency = cur.ToUpper().Trim();

            string message = "";
            if (CPH.TryGetArg("rawInput", out string ri) && !string.IsNullOrWhiteSpace(ri)) message = ri;
            else if (CPH.TryGetArg("message", out string msg) && !string.IsNullOrWhiteSpace(msg)) message = msg;

            string moneyPhrase = FormatMoneyWithDeclension(amount, currency);

            string alertText = string.IsNullOrWhiteSpace(message)
                ? "${tplNoMsg}".Replace("{user}", donorName).Replace("{amount}", moneyPhrase)
                : "${tplWithMsg}".Replace("{user}", donorName).Replace("{amount}", moneyPhrase).Replace("{message}", message.Trim());

            alertText = CleanForTTS(alertText);

            Directory.CreateDirectory(OutputDirectory);
            string json = "{\\"text\\":\\"" + EscapeJson(alertText) + "\\"${charArg}}";

            byte[] wav = RequestWav(json);
            if (wav == null)
            {
                CPH.LogError("DONATION: TTS-студия недоступна, донат не озвучен.");
                return false;
            }

            alertFileIndex = (alertFileIndex % 3) + 1;
            string outputFile = Path.Combine(OutputDirectory, "donate_" + alertFileIndex + ".wav");
            File.WriteAllBytes(outputFile, wav);

            CPH.PlaySound(outputFile, 1.0f, true);
            CPH.LogInfo("=== EVENT: DONATION SUCCESS ===");
            return true;
        }
        catch (Exception ex)
        {
            CPH.LogError("DONATION EXCEPTION: " + ex.ToString());
            return false;
        }
    }
` + getCommonHelpers(true, false, serverUrls) + `
}`;
        } else {
            let phrasesArr = [];
            if (phrasesContainer) {
                const inputs = phrasesContainer.querySelectorAll('.phrase-input');
                phrasesArr = Array.from(inputs).map(i => i.value.trim()).filter(Boolean);
            }
            if (phrasesArr.length === 0) {
                phrasesArr = defaultPhrases[type] || ["Привет, {user}!"];
            }

            const phrasesCode = phrasesArr.map(p => `        "${p.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`).join(',\n');
            const isRaid = (type === 'raid');

            code = `using System;
using System.IO;
using System.Text;
using System.Text.RegularExpressions;
using System.Net.Http;
using System.Threading.Tasks;

public class CPHInline
{
    private static readonly HttpClient client = new HttpClient();
    private static readonly string OutputDirectory = Path.Combine(Path.GetTempPath(), "TTS_Stream_Buffer");
    private static int alertFileIndex = 0;
    private static readonly Random random = new Random();

    private static readonly string[] Templates = new string[]
    {
${phrasesCode}
    };

    public bool Execute()
    {
        try
        {
            CPH.LogInfo("=== EVENT: ${type.toUpperCase()} ===");

            string userName = "Зритель";
            if (CPH.TryGetArg("user", out string u) && !string.IsNullOrWhiteSpace(u)) userName = u;
            else if (CPH.TryGetArg("userName", out string un) && !string.IsNullOrWhiteSpace(un)) userName = un;
`;

            if (isRaid) {
                code += `
            int viewers = 1;
            if (CPH.TryGetArg("viewers", out int vCount)) viewers = vCount;
            else if (CPH.TryGetArg("viewerCount", out int vc)) viewers = vc;

            string viewersPhrase = viewers.ToString() + " " + GetHumanDeclension(viewers);
            string template = Templates[random.Next(Templates.Length)];
            string alertText = CleanForTTS(template.Replace("{streamer}", userName).Replace("{viewers_phrase}", viewersPhrase));`;
            } else {
                code += `
            string template = Templates[random.Next(Templates.Length)];
            string alertText = CleanForTTS(template.Replace("{user}", userName));`;
            }

            code += `

            Directory.CreateDirectory(OutputDirectory);
            string json = "{\\"text\\":\\"" + EscapeJson(alertText) + "\\"${charArg}}";

            byte[] wav = RequestWav(json);
            if (wav == null)
            {
                CPH.LogError("${type.toUpperCase()}: TTS-студия недоступна.");
                return false;
            }

            alertFileIndex = (alertFileIndex % 3) + 1;
            string outputFile = Path.Combine(OutputDirectory, "${type}_" + alertFileIndex + ".wav");
            File.WriteAllBytes(outputFile, wav);

            CPH.PlaySound(outputFile, 1.0f, true);
            CPH.LogInfo("=== EVENT: ${type.toUpperCase()} SUCCESS ===");
            return true;
        }
        catch (Exception ex)
        {
            CPH.LogError("${type.toUpperCase()} EXCEPTION: " + ex.ToString());
            return false;
        }
    }
` + getCommonHelpers(false, isRaid, serverUrls) + `
}`;
        }

        codeBox.innerText = code;
    }

    eventTypeSel.addEventListener('change', updateFormVisibility);
    if (phraseModeSel) {
        phraseModeSel.addEventListener('change', () => {
            renderPhraseInputs(eventTypeSel.value, phraseModeSel.value);
            updateGeneratedCode();
        });
    }
    if (charSelect) charSelect.addEventListener('change', updateGeneratedCode);
    if (maxLenInp) maxLenInp.addEventListener('input', updateGeneratedCode);
    if (limitActionSel) limitActionSel.addEventListener('change', updateGeneratedCode);
    if (limitTextInp) limitTextInp.addEventListener('input', updateGeneratedCode);
    if (donateNoMsgInp) donateNoMsgInp.addEventListener('input', updateGeneratedCode);
    if (donateWithMsgInp) donateWithMsgInp.addEventListener('input', updateGeneratedCode);

    if (cfgHostInp) cfgHostInp.addEventListener('input', updateGeneratedCode);
    if (cfgPortInp) cfgPortInp.addEventListener('input', updateGeneratedCode);

    if (btnCopyGen) {
        btnCopyGen.addEventListener('click', () => {
            copySnippetText(codeBox.innerText);
        });
    }

    updateFormVisibility();
}
