package pt.horariosfamilia.r2a

import android.app.Activity
import android.app.AlertDialog
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.graphics.Typeface
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import io.github.muntashirakon.adb.AbsAdbConnectionManager
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private lateinit var ipField: EditText
    private lateinit var connectPortField: EditText
    private lateinit var pairPortField: EditText
    private lateinit var pairCodeField: EditText
    private lateinit var resultView: TextView
    private lateinit var progress: ProgressBar
    private lateinit var statusView: TextView
    private lateinit var pairStatusView: TextView
    private val prefs by lazy { getSharedPreferences("r2a_manager", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(buildUi())
    }

    private fun buildUi(): View {
        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(18), dp(18), dp(28))
        }
        scroll.addView(root)

        root.addView(TextView(this).apply {
            text = "R2A — Diagnóstico e Gestão v1.6 Stable"
            textSize = 24f
            setTypeface(typeface, Typeface.BOLD)
        })
        root.addView(TextView(this).apply {
            text = "Liga este telemóvel e a box DIGI R2A à mesma rede. A app executa os testes na box, não no telemóvel."
            textSize = 15f
            setPadding(0, dp(6), 0, dp(12))
        })

        root.addView(label("IP da box R2A"))
        ipField = edit(prefs.getString("ip", "192.168.1.204") ?: "192.168.1.204", "ex.: 192.168.1.45", false)
        root.addView(ipField)

        root.addView(label("Porta de ligação ADB"))
        connectPortField = edit(prefs.getString("connect_port", "34935") ?: "34935", "ex.: 5555 ou porta do Wireless debugging", true)
        root.addView(connectPortField)

        root.addView(label("Porta de emparelhamento (só Android 11+ / Wireless debugging)"))
        pairPortField = edit(prefs.getString("pair_port", "") ?: "", "ex.: 37123", true)
        root.addView(pairPortField)

        root.addView(label("Código de emparelhamento"))
        pairCodeField = edit("", "6 dígitos mostrados na box", true)
        root.addView(pairCodeField)

        root.addView(button("1. EMPARELHAR ADB") { pairDevice() })
        pairStatusView = TextView(this).apply {
            text = "Emparelhamento preservado. A v1.6 consegue executar e recolher automaticamente o relatório da Sonda DRM instalada na R2A."
            textSize = 13f
            setPadding(dp(6), dp(2), dp(6), dp(8))
        }
        root.addView(pairStatusView)
        root.addView(button("2. TESTAR LIGAÇÃO") { testConnection() })
        root.addView(button("3. DIAGNÓSTICO COMPLETO") { fullDiagnostic() })
        root.addView(button("4. DIAGNÓSTICO NETFLIX / DRM") { netflixDiagnostic() })
        root.addView(button("5. EXECUTAR/LER SONDA DRM") { runAndReadDrmProbe() })

        val row1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        row1.addView(button("Abrir Netflix", 1f) { remoteCommand("Abrir Netflix", "monkey -p com.netflix.ninja -c android.intent.category.LAUNCHER 1") })
        row1.addView(button("Fechar Netflix", 1f) { remoteCommand("Fechar Netflix", "am force-stop com.netflix.ninja") })
        root.addView(row1)

        val row2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        row2.addView(button("Copiar relatório", 1f) { copyReport() })
        row2.addView(button("Limpar", 1f) {
            resultView.text = ""
            statusView.text = "Pronto."
            pairStatusView.text = "Emparelhamento preservado. Usa diretamente «2. TESTAR LIGAÇÃO»."
        })
        root.addView(row2)

        root.addView(button("REINICIAR BOX", null) {
            AlertDialog.Builder(this)
                .setTitle("Reiniciar a R2A?")
                .setMessage("A box será reiniciada imediatamente através de ADB.")
                .setNegativeButton("Cancelar", null)
                .setPositiveButton("Reiniciar") { _, _ -> remoteCommand("Reiniciar box", "reboot") }
                .show()
        })

        progress = ProgressBar(this).apply {
            visibility = View.GONE
            isIndeterminate = true
        }
        root.addView(progress)

        statusView = TextView(this).apply {
            text = "Pronto."
            textSize = 15f
            setPadding(0, dp(12), 0, dp(8))
            setTypeface(typeface, Typeface.BOLD)
        }
        root.addView(statusView)

        resultView = TextView(this).apply {
            textSize = 13f
            setTextIsSelectable(true)
            typeface = Typeface.MONOSPACE
            setPadding(dp(10), dp(10), dp(10), dp(10))
        }
        root.addView(resultView)

        root.addView(TextView(this).apply {
            text = "Nota: Widevine L1 e alguns indicadores técnicos podem ser lidos por ADB, mas a certificação oficial Netflix e a resolução máxima autorizada pela Netflix não podem ser confirmadas apenas por estes comandos. O relatório separa esses indicadores da certificação."
            textSize = 12f
            setPadding(0, dp(16), 0, 0)
        })

        return scroll
    }

    private fun label(textValue: String) = TextView(this).apply {
        text = textValue
        textSize = 14f
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(8), 0, dp(3))
    }

    private fun edit(value: String, hintValue: String, numeric: Boolean) = EditText(this).apply {
        setText(value)
        hint = hintValue
        inputType = if (numeric) InputType.TYPE_CLASS_NUMBER else InputType.TYPE_CLASS_TEXT
        isSingleLine = true
        setPadding(dp(10), dp(8), dp(10), dp(8))
    }

    private fun button(textValue: String, weight: Float? = null, action: () -> Unit): Button {
        return Button(this).apply {
            text = textValue
            isAllCaps = false
            setOnClickListener { action() }
            layoutParams = if (weight == null) {
                LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                    setMargins(0, dp(5), 0, dp(5))
                }
            } else {
                LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight).apply {
                    setMargins(dp(2), dp(4), dp(2), dp(4))
                }
            }
        }
    }

    private fun pairDevice() {
        val host = hostOrWarn() ?: return
        val pairPort = pairPortField.text.toString().trim().toIntOrNull()
        val code = pairCodeField.text.toString().trim()
        if (pairPort == null || pairPort !in 1..65535 || code.length != 6) {
            toast("Indica a porta de emparelhamento e o código de 6 dígitos mostrado na R2A.")
            return
        }
        saveFields()
        pairStatusView.text = "A emparelhar… mantém o código visível na TV."
        busy(true, "A emparelhar com a R2A…")
        scope.launch {
            val result = runCatching {
                val manager = R2AAdbManager.getInstance(applicationContext)
                manager.setTimeout(15, TimeUnit.SECONDS)
                val ok = manager.pair(host, pairPort, code)
                if (!ok) throw IOException("A biblioteca ADB devolveu falha de emparelhamento.")
                "Emparelhamento concluído com o backend libadb. Agora toca em «2. TESTAR LIGAÇÃO»."
            }
            showResult("EMPARELHAMENTO ADB", result)
        }
    }

    private fun testConnection() {
        runWithDevice("TESTE DE LIGAÇÃO") { manager ->
            busy(true, "Ligação ADB estabelecida. A testar comando…")
            val echo = safeShell(manager, "echo R2A_MANAGER_OK")
            val model = safeShell(manager, "getprop ro.product.manufacturer; getprop ro.product.model; getprop ro.build.version.release")
            "Ligação ADB: OK\nResposta: " + echo + "\n\nDispositivo:\n" + model
        }
    }

    private fun fullDiagnostic() {
        runWithDevice("DIAGNÓSTICO COMPLETO") { manager ->
            val sb = StringBuilder()
            sb.append(reportHeader("DIAGNÓSTICO COMPLETO v1.5"))
            section(sb, "IDENTIFICAÇÃO", safeShell(manager,
                "echo Fabricante: \$(getprop ro.product.manufacturer); " +
                "echo Modelo: \$(getprop ro.product.model); " +
                "echo Dispositivo: \$(getprop ro.product.device); " +
                "echo Android: \$(getprop ro.build.version.release); " +
                "echo SDK: \$(getprop ro.build.version.sdk); " +
                "echo Patch: \$(getprop ro.build.version.security_patch); " +
                "echo Build: \$(getprop ro.build.display.id); " +
                "echo Fingerprint: \$(getprop ro.build.fingerprint)", 6000L))
            section(sb, "ECRÃ / HDMI", displayBlock(manager))
            section(sb, "CPU / ABI", safeShell(manager,
                "getprop ro.product.cpu.abi; getprop ro.product.cpu.abilist", 4000L))
            section(sb, "BOOT / BUILD", safeShell(manager,
                "echo verifiedbootstate=\$(getprop ro.boot.verifiedbootstate); " +
                "echo build_tags=\$(getprop ro.build.tags); " +
                "echo build_type=\$(getprop ro.build.type); " +
                "echo first_api=\$(getprop ro.product.first_api_level)", 4000L))
            section(sb, "GOOGLE / PLAY STORE", googleBlock(manager))
            section(sb, "NETFLIX", netflixBlock(manager))
            section(sb, "DRM / WIDEVINE", drmBlock(manager))
            section(sb, "CODECS / HDR", codecsBlock(manager))
            section(sb, "PROPRIEDADES NETFLIX/DRM", safeShell(manager,
                "getprop | grep -i -E 'netflix|widevine|drm' | head -160", 6000L))
            sb.append("\nINTERPRETAÇÃO\n")
            sb.append(interpretNetflix(manager))
            sb.toString()
        }
    }

    private fun netflixDiagnostic() {
        runWithDevice("NETFLIX / DRM") { manager ->
            val sb = StringBuilder()
            sb.append(reportHeader("DIAGNÓSTICO NETFLIX / DRM v1.5"))
            section(sb, "NETFLIX INSTALADA", netflixBlock(manager))
            section(sb, "DRM / WIDEVINE", drmBlock(manager))
            section(sb, "CODECS / HDR", codecsBlock(manager))
            section(sb, "DISPLAY / HDMI", displayBlock(manager))
            section(sb, "INDICADORES GOOGLE", googleBlock(manager))
            section(sb, "PROPRIEDADES DO SISTEMA", safeShell(manager,
                "getprop | grep -i -E 'netflix|widevine|drm|hdr|dolby' | head -200", 7000L))
            sb.append("\nINTERPRETAÇÃO\n")
            sb.append(interpretNetflix(manager))
            sb.toString()
        }
    }

    private fun netflixBlock(manager: AbsAdbConnectionManager): String {
        val tvPath = safeShell(manager, "pm path com.netflix.ninja", 4000L)
        val mobilePath = safeShell(manager, "pm path com.netflix.mediaclient", 4000L)
        val tvInfo = if (commandHasPositiveOutput(tvPath)) {
            safeShell(manager,
                "dumpsys package com.netflix.ninja 2>/dev/null | grep -E 'versionName=|versionCode=|installerPackageName=|firstInstallTime=|lastUpdateTime=' | head -30",
                12000L)
        } else "(não executado: pacote Android TV não confirmado)"
        val mobileInfo = if (commandHasPositiveOutput(mobilePath)) {
            safeShell(manager,
                "dumpsys package com.netflix.mediaclient 2>/dev/null | grep -E 'versionName=|versionCode=|installerPackageName=|firstInstallTime=|lastUpdateTime=' | head -30",
                12000L)
        } else "(não executado: pacote móvel não confirmado)"
        val props = safeShell(manager, "getprop | grep -i netflix | head -80", 5000L)
        return "com.netflix.ninja (Android TV):\n" + tvPath +
            "\n\nDetalhes Android TV:\n" + tvInfo +
            "\n\ncom.netflix.mediaclient (móvel):\n" + mobilePath +
            "\n\nDetalhes móvel:\n" + mobileInfo +
            "\n\nPropriedades Netflix:\n" + props
    }

    private fun drmBlock(manager: AbsAdbConnectionManager): String {
        val props = safeShell(manager,
            "getprop | grep -i -E 'widevine|drm|mediadrm' | head -140", 6000L)
        val services = safeShell(manager,
            "service list 2>/dev/null | grep -i -E 'drm|media' | head -100", 6000L)
        val libs = safeShell(manager,
            "for d in /vendor/lib/mediadrm /vendor/lib64/mediadrm /vendor/lib/drm /vendor/lib64/drm /odm/lib/mediadrm /odm/lib64/mediadrm; do [ -d \"\$d\" ] && ls \"\$d\"; done 2>/dev/null | grep -i -E 'widevine|drm' | head -80",
            6000L)
        val dump = safeShell(manager,
            "dumpsys media.drm 2>/dev/null | grep -i -E 'widevine|security.?level|vendor|version|oemcrypto' | head -180",
            18000L)
        return "Propriedades:\n" + props +
            "\n\nServiços DRM/media:\n" + services +
            "\n\nBibliotecas DRM:\n" + libs +
            "\n\ndumpsys media.drm:\n" + dump
    }

    private fun codecsBlock(manager: AbsAdbConnectionManager): String {
        val xml = safeShell(manager,
            "grep -h -i -E 'video/(avc|hevc|x-vnd.on2.vp9|av01|dolby-vision)|hdr|dolby' /vendor/etc/media_codecs*.xml /odm/etc/media_codecs*.xml /system/etc/media_codecs*.xml 2>/dev/null | head -180",
            10000L)
        val props = safeShell(manager,
            "getprop | grep -i -E 'codec|hevc|vp9|av1|hdr|dolby|display' | head -180",
            7000L)
        return "Ficheiros media_codecs*.xml:\n" + xml + "\n\nPropriedades codec/display:\n" + props
    }

    private fun displayBlock(manager: AbsAdbConnectionManager): String {
        val basic = safeShell(manager, "wm size; wm density", 4000L)
        val sf = safeShell(manager,
            "dumpsys SurfaceFlinger 2>/dev/null | grep -i -E 'Display|HDR|Dolby|color mode|active mode' | head -120",
            12000L)
        return basic + "\n\nSurfaceFlinger (amostra):\n" + sf
    }

    private fun googleBlock(manager: AbsAdbConnectionManager): String {
        val packages = safeShell(manager,
            "pm path com.android.vending; pm path com.google.android.gms; pm path com.google.android.gsf",
            5000L)
        val integrity = safeShell(manager,
            "echo verifiedbootstate=\$(getprop ro.boot.verifiedbootstate); " +
            "echo build_tags=\$(getprop ro.build.tags); " +
            "echo build_type=\$(getprop ro.build.type); " +
            "echo fingerprint=\$(getprop ro.build.fingerprint)",
            5000L)
        return "Pacotes Google:\n" + packages + "\n\nIndicadores de integridade/build:\n" + integrity
    }

    private fun interpretNetflix(manager: AbsAdbConnectionManager): String {
        val tvPath = safeShell(manager, "pm path com.netflix.ninja", 4000L)
        val mobilePath = safeShell(manager, "pm path com.netflix.mediaclient", 4000L)
        val drm = drmBlock(manager)
        val props = safeShell(manager, "getprop | grep -i netflix | head -80", 5000L)

        val tvState = commandState(tvPath)
        val mobileState = commandState(mobilePath)
        val low = drm.lowercase(Locale.ROOT)
        val l1Hint = Regex("""security.?level[^\n]*l1|\bl1\b[^\n]*widevine|widevine[^\n]*\bl1\b""").containsMatchIn(low)
        val l3Hint = Regex("""security.?level[^\n]*l3|\bl3\b[^\n]*widevine|widevine[^\n]*\bl3\b""").containsMatchIn(low)
        val drmIndeterminate = drm.contains("TIMEOUT", true) || drm.contains("[erro", true)
        val netflixProps = commandHasPositiveOutput(props)

        return buildString {
            append("• Netflix Android TV: ")
            append(when (tvState) {
                "FOUND" -> "com.netflix.ninja está instalada."
                "ABSENT" -> "com.netflix.ninja não foi encontrada."
                else -> "não foi possível determinar com segurança."
            })
            append("\n• Netflix móvel: ")
            append(when (mobileState) {
                "FOUND" -> "com.netflix.mediaclient está instalada."
                "ABSENT" -> "com.netflix.mediaclient não foi encontrada."
                else -> "não foi possível determinar com segurança."
            })
            append("\n• Widevine: ")
            append(when {
                l1Hint -> "foram encontrados indicadores explícitos de L1; confirmar no bloco DRM."
                l3Hint -> "foram encontrados indicadores explícitos de L3; confirmar no bloco DRM."
                drmIndeterminate -> "o teste ficou incompleto; nível L1/L3 não determinado."
                else -> "o firmware não expôs explicitamente o nível L1/L3 aos comandos usados."
            })
            append("\n• Integração Netflix no firmware: ")
            append(if (netflixProps) "existem propriedades específicas Netflix." else "não foram obtidas propriedades específicas Netflix.")
            append("\n• Certificação Netflix: estes testes não equivalem à certificação oficial Netflix/ESN. Widevine, presença da app e certificação são verificações diferentes.")
        }
    }

    private fun commandState(value: String): String {
        if (value.contains("TIMEOUT", true) || value.startsWith("[erro", true)) return "UNKNOWN"
        if (value.contains("package:", true)) return "FOUND"
        if (value.contains("(comando concluído sem saída)", true)) return "ABSENT"
        return if (value.isBlank()) "ABSENT" else "UNKNOWN"
    }

    private fun commandHasPositiveOutput(value: String): Boolean {
        return value.isNotBlank() &&
            !value.contains("(comando concluído sem saída)", true) &&
            !value.contains("TIMEOUT", true) &&
            !value.startsWith("[erro", true)
    }

    private fun runAndReadDrmProbe() {
        runWithDevice("SONDA DRM") { manager ->
            busy(true, "A abrir a Sonda DRM na R2A e a aguardar o relatório…")
            val command =
                "rm -f /sdcard/Download/R2A_DRM_PROBE.txt /storage/emulated/0/Download/R2A_DRM_PROBE.txt 2>/dev/null; " +
                "monkey -p pt.horariosfamilia.r2a.drmprobe -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; " +
                "i=0; while [ \$i -lt 20 ]; do " +
                "if [ -s /sdcard/Download/R2A_DRM_PROBE.txt ]; then cat /sdcard/Download/R2A_DRM_PROBE.txt; exit 0; fi; " +
                "if [ -s /storage/emulated/0/Download/R2A_DRM_PROBE.txt ]; then cat /storage/emulated/0/Download/R2A_DRM_PROBE.txt; exit 0; fi; " +
                "sleep 1; i=\$((i+1)); done; echo __R2A_PROBE_NOT_FOUND__"
            val report = safeShell(manager, command, 30000L)
            if (report.contains("__R2A_PROBE_NOT_FOUND__")) {
                "A Sonda DRM não produziu o ficheiro esperado. Confirma que a APK «R2A DRM Probe» está instalada na box e volta a tentar."
            } else {
                report
            }
        }
    }

    private fun remoteCommand(title: String, command: String) {
        runWithDevice(title.uppercase(Locale.ROOT)) { manager ->
            safeShell(manager, command).ifBlank { "Comando enviado." }
        }
    }

    private fun runWithDevice(title: String, block: (AbsAdbConnectionManager) -> String) {
        val host = hostOrWarn() ?: return
        val port = connectPortField.text.toString().trim().toIntOrNull()
        if (port == null || port !in 1..65535) {
            toast("Indica uma porta ADB válida.")
            return
        }
        saveFields()
        busy(true, "A ligar à R2A em " + host + ":" + port + "…")
        scope.launch {
            val result = runCatching {
                var manager = R2AAdbManager.getInstance(applicationContext)
                manager.setTimeout(8, TimeUnit.SECONDS)

                var connected = manager.isConnected
                if (!connected) {
                    connected = runCatching { manager.connect(host, port) }.getOrDefault(false)
                }

                if (!connected) {
                    busy(true, "Ligação direta falhou. A procurar a R2A automaticamente…")
                    manager = R2AAdbManager.recreate(applicationContext)
                    manager.setTimeout(8, TimeUnit.SECONDS)
                    connected = runCatching { manager.connectTls(applicationContext, 6000) }.getOrDefault(false)
                }

                if (!connected && !manager.isConnected) {
                    throw IOException("Não foi possível estabelecer a ligação ADB por porta direta nem por deteção automática.")
                }

                busy(true, "Ligação ADB estabelecida.")
                block(manager)
            }
            showResult(title, result)
        }
    }

    private fun safeShell(
        manager: AbsAdbConnectionManager,
        command: String,
        timeoutMs: Long = 8000L
    ): String {
        return runCatching {
            val marker = "__R2A_END_" + System.nanoTime() + "__"
            val stream = manager.openStream("shell:" + command + "; echo " + marker)
            val output = ByteArrayOutputStream()
            var completed = false
            try {
                val input = stream.openInputStream()
                val buffer = ByteArray(4096)
                val deadline = System.currentTimeMillis() + timeoutMs
                while (System.currentTimeMillis() < deadline) {
                    val available = runCatching { input.available() }.getOrElse { break }
                    if (available > 0) {
                        val count = input.read(buffer, 0, minOf(buffer.size, available))
                        if (count > 0) {
                            output.write(buffer, 0, count)
                            val current = output.toString(StandardCharsets.UTF_8.name())
                            if (current.contains(marker)) {
                                completed = true
                                break
                            }
                        }
                    } else {
                        if (stream.isClosed) break
                        Thread.sleep(35)
                    }
                }
            } finally {
                runCatching { stream.close() }
            }
            val text = output.toString(StandardCharsets.UTF_8.name())
                .replace(marker, "")
                .trim()
            when {
                completed && text.isBlank() -> "(comando concluído sem saída)"
                completed -> text
                text.isNotBlank() -> text + "\n(TIMEOUT após " + (timeoutMs / 1000) + " s; saída parcial)"
                else -> "(TIMEOUT após " + (timeoutMs / 1000) + " s; sem saída)"
            }
        }.getOrElse { "[erro ao executar] " + (it.message ?: it.javaClass.simpleName) }
    }

    private fun section(sb: StringBuilder, title: String, body: String) {
        sb.append("\n===== ").append(title).append(" =====\n")
        sb.append(if (body.isBlank()) "(sem dados)" else body).append("\n")
    }

    private fun reportHeader(title: String): String {
        val whenText = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())
        return title + "\nData: " + whenText + "\nIP: " + ipField.text.toString().trim() + ":" + connectPortField.text.toString().trim() + "\n"
    }

    private fun showResult(title: String, result: Result<String>) {
        runOnUiThread {
            busy(false, if (result.isSuccess) "Concluído." else "Falhou.")
            if (result.isSuccess) {
                val message = result.getOrNull().orEmpty()
                resultView.text = title + "\n\n" + message
                if (title == "EMPARELHAMENTO ADB") {
                    pairStatusView.text = "✓ Emparelhado. Agora toca em «2. TESTAR LIGAÇÃO»."
                }
            } else {
                val error = result.exceptionOrNull()
                val raw = error?.message ?: error?.javaClass?.simpleName ?: "desconhecido"
                val hint = if (title == "EMPARELHAMENTO ADB") {
                    "Gera um NOVO código na R2A antes de repetir. O emparelhamento já está guardado. Não voltes a emparelhar a menos que a app indique explicitamente que é necessário."
                } else {
                    "Confirma que a Depuração sem fios continua ativada e que a porta de LIGAÇÃO ADB é a mostrada no ecrã principal da R2A."
                }
                resultView.text = title + "\n\nERRO: " + raw + "\n\n" + hint
                if (title == "EMPARELHAMENTO ADB") {
                    pairStatusView.text = "✗ Emparelhamento falhou. Vê a explicação abaixo."
                }
            }
        }
    }

    private fun busy(isBusy: Boolean, message: String) {
        runOnUiThread {
            progress.visibility = if (isBusy) View.VISIBLE else View.GONE
            statusView.text = message
        }
    }

    private fun hostOrWarn(): String? {
        val host = ipField.text.toString().trim()
        if (host.isBlank()) {
            toast("Indica o IP da R2A.")
            return null
        }
        return host
    }

    private fun saveFields() {
        prefs.edit()
            .putString("ip", ipField.text.toString().trim())
            .putString("connect_port", connectPortField.text.toString().trim())
            .putString("pair_port", pairPortField.text.toString().trim())
            .apply()
    }

    private fun copyReport() {
        val textValue = resultView.text.toString()
        if (textValue.isBlank()) {
            toast("Ainda não existe relatório para copiar.")
            return
        }
        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("Relatório R2A", textValue))
        toast("Relatório copiado.")
    }

    private fun toast(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }


}
