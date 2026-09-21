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
            text = "R2A — Diagnóstico e Gestão v1.3"
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
            text = "Backend ADB alternativo. Faz um novo emparelhamento apenas depois de remover o registo antigo «R2A-Diagnostico» na box."
            textSize = 13f
            setPadding(dp(6), dp(2), dp(6), dp(8))
        }
        root.addView(pairStatusView)
        root.addView(button("2. TESTAR LIGAÇÃO") { testConnection() })
        root.addView(button("3. DIAGNÓSTICO COMPLETO") { fullDiagnostic() })
        root.addView(button("4. DIAGNÓSTICO NETFLIX / DRM") { netflixDiagnostic() })

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
            pairStatusView.text = "Emparelhamento ainda não efetuado."
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
            val echo = safeShell(manager, "echo R2A_MANAGER_OK")
            val model = safeShell(manager, "getprop ro.product.manufacturer; getprop ro.product.model; getprop ro.build.version.release")
            "Resposta: " + echo + "\n\nDispositivo:\n" + model
        }
    }

    private fun fullDiagnostic() {
        runWithDevice("DIAGNÓSTICO COMPLETO") { manager ->
            val sb = StringBuilder()
            sb.append(reportHeader("DIAGNÓSTICO COMPLETO"))
            section(sb, "IDENTIFICAÇÃO", safeShell(manager,
                "echo Fabricante: \$(getprop ro.product.manufacturer); " +
                "echo Modelo: \$(getprop ro.product.model); " +
                "echo Dispositivo: \$(getprop ro.product.device); " +
                "echo Android: \$(getprop ro.build.version.release); " +
                "echo SDK: \$(getprop ro.build.version.sdk); " +
                "echo Patch: \$(getprop ro.build.version.security_patch); " +
                "echo Build: \$(getprop ro.build.display.id)"))
            section(sb, "ECRÃ", safeShell(manager, "wm size; wm density"))
            section(sb, "CPU / ABI", safeShell(manager, "getprop ro.product.cpu.abi; getprop ro.product.cpu.abilist"))
            section(sb, "BOOT / BUILD", safeShell(manager,
                "echo verifiedbootstate=\$(getprop ro.boot.verifiedbootstate); " +
                "echo build_tags=\$(getprop ro.build.tags); " +
                "echo build_type=\$(getprop ro.build.type)"))
            section(sb, "GOOGLE / PLAY STORE", safeShell(manager,
                "pm list packages | grep -E 'com.google.android.gms|com.android.vending|com.google.android.gsf'"))
            section(sb, "NETFLIX", netflixBlock(manager))
            section(sb, "DRM / WIDEVINE", drmBlock(manager))
            section(sb, "PROPRIEDADES NETFLIX/DRM", safeShell(manager,
                "getprop | grep -i -E 'netflix|widevine|drm' | head -120"))
            section(sb, "CODECS (amostra)", safeShell(manager,
                "dumpsys media.codec 2>/dev/null | grep -i -E 'video/avc|video/hevc|video/x-vnd.on2.vp9|video/av01' | head -120"))
            sb.append("\nINTERPRETAÇÃO\n")
            sb.append(interpretNetflix(manager))
            sb.toString()
        }
    }

    private fun netflixDiagnostic() {
        runWithDevice("NETFLIX / DRM") { manager ->
            val sb = StringBuilder()
            sb.append(reportHeader("DIAGNÓSTICO NETFLIX / DRM"))
            section(sb, "NETFLIX INSTALADA", netflixBlock(manager))
            section(sb, "DRM / WIDEVINE", drmBlock(manager))
            section(sb, "PROPRIEDADES DO SISTEMA", safeShell(manager,
                "getprop | grep -i -E 'netflix|widevine|drm' | head -160"))
            section(sb, "DISPLAY", safeShell(manager, "wm size; wm density"))
            section(sb, "INDICADORES GOOGLE", safeShell(manager,
                "pm list packages | grep -E 'com.google.android.gms|com.android.vending|com.google.android.gsf'; " +
                "echo build_tags=\$(getprop ro.build.tags); echo verifiedbootstate=\$(getprop ro.boot.verifiedbootstate)"))
            sb.append("\nINTERPRETAÇÃO\n")
            sb.append(interpretNetflix(manager))
            sb.toString()
        }
    }

    private fun netflixBlock(manager: AbsAdbConnectionManager): String {
        val packages = safeShell(manager, "pm list packages | grep -i netflix")
        val tv = safeShell(manager,
            "dumpsys package com.netflix.ninja 2>/dev/null | grep -E 'versionName=|versionCode=|installerPackageName|firstInstallTime|lastUpdateTime' | head -30")
        val mobile = safeShell(manager,
            "dumpsys package com.netflix.mediaclient 2>/dev/null | grep -E 'versionName=|versionCode=|installerPackageName|firstInstallTime|lastUpdateTime' | head -30")
        return "Pacotes:\n" + packages + "\n\ncom.netflix.ninja:\n" + tv + "\n\ncom.netflix.mediaclient:\n" + mobile
    }

    private fun drmBlock(manager: AbsAdbConnectionManager): String {
        val a = safeShell(manager,
            "dumpsys media.drm 2>/dev/null | grep -i -E 'widevine|securityLevel|security level|vendor|version' | head -160")
        val b = safeShell(manager,
            "getprop | grep -i -E 'widevine|drm' | head -120")
        return "dumpsys media.drm:\n" + a + "\n\ngetprop:\n" + b
    }

    private fun interpretNetflix(manager: AbsAdbConnectionManager): String {
        val pkgs = safeShell(manager, "pm list packages | grep -i netflix")
        val drm = drmBlock(manager)
        val props = safeShell(manager, "getprop | grep -i netflix")
        val hasTvNetflix = pkgs.contains("com.netflix.ninja")
        val hasAnyNetflix = pkgs.contains("netflix", ignoreCase = true)
        val low = drm.lowercase(Locale.ROOT)
        val l1Hint = low.contains("securitylevel") && low.contains("l1") ||
            low.contains("security level") && low.contains("l1")
        val netflixProps = props.isNotBlank()

        return buildString {
            append("• App Netflix: ")
            append(if (hasTvNetflix) "com.netflix.ninja detetada (versão Android TV)." else if (hasAnyNetflix) "foi detetado um pacote Netflix." else "não foi detetada.")
            append("\n• Widevine: ")
            append(if (l1Hint) "o relatório contém uma referência compatível com L1; confirmar no bloco DRM." else "não foi possível confirmar L1 automaticamente.")
            append("\n• Propriedades específicas Netflix: ")
            append(if (netflixProps) "existem propriedades do sistema com referência a Netflix." else "não foram encontradas propriedades evidentes.")
            append("\n• Certificação Netflix: NÃO é declarada por esta app. Mesmo com Widevine L1, a autorização de HD/Full HD/4K depende também da certificação/ESN e das políticas da Netflix.")
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
        busy(true, "A ligar à R2A…")
        scope.launch {
            val result = runCatching {
                val manager = R2AAdbManager.getInstance(applicationContext)
                manager.setTimeout(15, TimeUnit.SECONDS)
                runCatching { manager.disconnect() }
                val connected = manager.connect(host, port)
                if (!connected && !manager.isConnected) {
                    throw IOException("Não foi possível estabelecer a ligação ADB à R2A.")
                }
                block(manager)
            }
            showResult(title, result)
        }
    }

    private fun safeShell(manager: AbsAdbConnectionManager, command: String): String {
        return runCatching {
            val stream = manager.openStream("shell:" + command)
            val output = ByteArrayOutputStream()
            try {
                val input = stream.openInputStream()
                val buffer = ByteArray(4096)
                while (true) {
                    val count = try { input.read(buffer) } catch (e: IOException) {
                        if (output.size() > 0) break else throw e
                    }
                    if (count <= 0) break
                    output.write(buffer, 0, count)
                }
            } finally {
                runCatching { stream.close() }
            }
            output.toString(StandardCharsets.UTF_8.name()).trim()
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
                    "Gera um NOVO código na R2A antes de repetir. A v1.2 usa um backend ADB diferente (libadb-android), mantendo o IP e a porta de ligação já preenchidos."
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
