package pt.horariosfamilia.r2a.drmprobe;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.graphics.Typeface;
import android.media.MediaDrm;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final UUID WIDEVINE_UUID =
            UUID.fromString("edef8ba9-79d6-4ace-a3c8-27dcd51d21ed");
    private static final String REPORT_NAME = "R2A_DRM_PROBE.txt";

    private TextView summaryView;
    private TextView reportView;
    private TextView statusView;
    private ProgressBar progress;
    private String lastReport = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildUi());
        runProbe();
    }

    private View buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(28), dp(24), dp(28), dp(32));
        scroll.addView(root);

        TextView title = new TextView(this);
        title.setText("R2A — Sonda DRM / Widevine");
        title.setTextSize(28f);
        title.setTypeface(title.getTypeface(), Typeface.BOLD);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Consulta diretamente a API MediaDrm da DIGI R2A e grava o relatório em Download/" + REPORT_NAME + ".");
        subtitle.setTextSize(17f);
        subtitle.setPadding(0, dp(8), 0, dp(16));
        root.addView(subtitle);

        summaryView = new TextView(this);
        summaryView.setText("A preparar diagnóstico…");
        summaryView.setTextSize(20f);
        summaryView.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        summaryView.setPadding(dp(12), dp(12), dp(12), dp(12));
        root.addView(summaryView);

        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        buttons.setGravity(Gravity.CENTER);

        Button run = button("EXECUTAR NOVAMENTE");
        run.setOnClickListener(v -> runProbe());
        buttons.addView(run, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        Button save = button("GUARDAR RELATÓRIO");
        save.setOnClickListener(v -> {
            if (lastReport.isEmpty()) {
                toast("Ainda não existe relatório.");
            } else {
                saveReport(lastReport, true);
            }
        });
        buttons.addView(save, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));

        root.addView(buttons);

        progress = new ProgressBar(this);
        progress.setIndeterminate(true);
        progress.setVisibility(View.GONE);
        root.addView(progress);

        statusView = new TextView(this);
        statusView.setText("Pronto.");
        statusView.setTextSize(16f);
        statusView.setPadding(0, dp(10), 0, dp(8));
        root.addView(statusView);

        reportView = new TextView(this);
        reportView.setTextSize(14f);
        reportView.setTypeface(Typeface.MONOSPACE);
        reportView.setTextIsSelectable(true);
        reportView.setPadding(dp(10), dp(10), dp(10), dp(10));
        root.addView(reportView);

        return scroll;
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setFocusable(true);
        b.setMinHeight(dp(58));
        return b;
    }

    private void runProbe() {
        progress.setVisibility(View.VISIBLE);
        statusView.setText("A consultar MediaDrm/Widevine…");
        summaryView.setText("Diagnóstico em curso…");

        new Thread(() -> {
            ProbeResult result = probe();
            lastReport = result.report;
            saveReport(result.report, false);
            runOnUiThread(() -> {
                progress.setVisibility(View.GONE);
                statusView.setText("Concluído. Relatório guardado em Download/" + REPORT_NAME);
                summaryView.setText(result.summary);
                reportView.setText(result.report);
            });
        }).start();
    }

    private ProbeResult probe() {
        StringBuilder out = new StringBuilder();
        String now = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(new Date());
        out.append("R2A DRM PROBE\n");
        out.append("Data: ").append(now).append("\n");
        out.append("Fabricante: ").append(Build.MANUFACTURER).append("\n");
        out.append("Modelo: ").append(Build.MODEL).append("\n");
        out.append("Android: ").append(Build.VERSION.RELEASE).append(" (SDK ").append(Build.VERSION.SDK_INT).append(")\n");
        out.append("Build: ").append(Build.DISPLAY).append("\n\n");

        boolean supported = false;
        try {
            supported = MediaDrm.isCryptoSchemeSupported(WIDEVINE_UUID);
        } catch (Throwable t) {
            out.append("Widevine suportado: ERRO — ").append(shortError(t)).append("\n");
        }
        out.append("Widevine UUID: ").append(WIDEVINE_UUID).append("\n");
        out.append("Widevine suportado: ").append(supported ? "SIM" : "NÃO").append("\n");

        String propSecurity = "(não disponível)";
        String sessionSecurity = "(não disponível)";
        String maxSecurity = "(não disponível)";
        String connectedHdcp = "(não disponível)";
        String maxHdcp = "(não disponível)";

        if (Build.VERSION.SDK_INT >= 30) {
            try {
                List<UUID> schemes = MediaDrm.getSupportedCryptoSchemes();
                out.append("Esquemas DRM suportados: ").append(schemes).append("\n");
            } catch (Throwable t) {
                out.append("Esquemas DRM suportados: ERRO — ").append(shortError(t)).append("\n");
            }
        }

        out.append("\n===== WIDEVINE MEDIADRM =====\n");

        if (supported) {
            MediaDrm drm = null;
            byte[] session = null;
            try {
                drm = new MediaDrm(WIDEVINE_UUID);

                out.append("Vendor: ").append(safeProperty(drm, MediaDrm.PROPERTY_VENDOR)).append("\n");
                out.append("Version: ").append(safeProperty(drm, MediaDrm.PROPERTY_VERSION)).append("\n");
                out.append("Description: ").append(safeProperty(drm, MediaDrm.PROPERTY_DESCRIPTION)).append("\n");
                out.append("Algorithms: ").append(safeProperty(drm, MediaDrm.PROPERTY_ALGORITHMS)).append("\n");

                propSecurity = safeProperty(drm, "securityLevel");
                out.append("securityLevel (propriedade Widevine): ").append(propSecurity).append("\n");
                out.append("systemId: ").append(safeProperty(drm, "systemId")).append("\n");
                out.append("privacyMode: ").append(safeProperty(drm, "privacyMode")).append("\n");
                out.append("sessionSharing: ").append(safeProperty(drm, "sessionSharing")).append("\n");
                out.append("usageReportingSupport: ").append(safeProperty(drm, "usageReportingSupport")).append("\n");
                out.append("oemCryptoBuildInformation: ").append(safeProperty(drm, "oemCryptoBuildInformation")).append("\n");
                out.append("hdcpLevel (propriedade): ").append(safeProperty(drm, "hdcpLevel")).append("\n");
                out.append("maxHdcpLevel (propriedade): ").append(safeProperty(drm, "maxHdcpLevel")).append("\n");

                if (Build.VERSION.SDK_INT >= 28) {
                    int maxSec = MediaDrm.getMaxSecurityLevel();
                    maxSecurity = securityLevelName(maxSec);
                    out.append("MediaDrm.getMaxSecurityLevel(): ").append(maxSecurity)
                            .append(" (").append(maxSec).append(")\n");

                    int connected = drm.getConnectedHdcpLevel();
                    int maximum = drm.getMaxHdcpLevel();
                    connectedHdcp = hdcpLevelName(connected);
                    maxHdcp = hdcpLevelName(maximum);
                    out.append("HDCP ligado: ").append(connectedHdcp).append(" (").append(connected).append(")\n");
                    out.append("HDCP máximo: ").append(maxHdcp).append(" (").append(maximum).append(")\n");
                    out.append("Sessões máximas: ").append(drm.getMaxSessionCount()).append("\n");
                    out.append("Sessões abertas: ").append(drm.getOpenSessionCount()).append("\n");
                }

                try {
                    session = drm.openSession();
                    out.append("openSession(): OK\n");
                    if (Build.VERSION.SDK_INT >= 28) {
                        int sec = drm.getSecurityLevel(session);
                        sessionSecurity = securityLevelName(sec);
                        out.append("Segurança da sessão: ").append(sessionSecurity)
                                .append(" (").append(sec).append(")\n");
                    }
                } catch (Throwable t) {
                    out.append("openSession(): ERRO — ").append(shortError(t)).append("\n");
                }

                out.append("\n===== MIME / DECODER SEGURO =====\n");
                String[] mimes = new String[] {
                        "video/avc",
                        "video/hevc",
                        "video/x-vnd.on2.vp9",
                        "video/av01"
                };
                for (String mime : mimes) {
                    boolean mimeSupported;
                    try {
                        mimeSupported = MediaDrm.isCryptoSchemeSupported(WIDEVINE_UUID, mime);
                        out.append(mime).append(": Widevine=").append(mimeSupported ? "SIM" : "NÃO");
                    } catch (Throwable t) {
                        out.append(mime).append(": Widevine=ERRO(").append(shortError(t)).append(")");
                    }

                    if (Build.VERSION.SDK_INT >= 31) {
                        try {
                            boolean secure = drm.requiresSecureDecoder(mime, MediaDrm.getMaxSecurityLevel());
                            out.append(", decoder seguro no nível máximo=").append(secure ? "SIM" : "NÃO");
                        } catch (Throwable t) {
                            out.append(", decoder seguro=ERRO(").append(shortError(t)).append(")");
                        }
                    }
                    out.append("\n");
                }

                if (Build.VERSION.SDK_INT >= 28) {
                    out.append("\n===== MÉTRICAS MEDIADRM =====\n");
                    try {
                        android.os.PersistableBundle metrics = drm.getMetrics();
                        for (String key : metrics.keySet()) {
                            Object value = metrics.get(key);
                            out.append(key).append("=").append(String.valueOf(value)).append("\n");
                        }
                    } catch (Throwable t) {
                        out.append("Métricas: ERRO — ").append(shortError(t)).append("\n");
                    }
                }

            } catch (Throwable t) {
                out.append("Falha ao inicializar Widevine MediaDrm: ").append(shortError(t)).append("\n");
            } finally {
                if (drm != null) {
                    if (session != null) {
                        try { drm.closeSession(session); } catch (Throwable ignored) {}
                    }
                    try { drm.close(); } catch (Throwable ignored) {}
                }
            }
        }

        out.append("\n===== INTERPRETAÇÃO TÉCNICA =====\n");
        if (!supported) {
            out.append("Widevine não foi disponibilizado à API MediaDrm.\n");
        } else {
            out.append("Widevine está disponível através da API MediaDrm.\n");
            out.append("securityLevel Widevine: ").append(propSecurity).append("\n");
            out.append("Segurança de sessão Android: ").append(sessionSecurity).append("\n");
            out.append("Nível máximo Android DRM: ").append(maxSecurity).append("\n");
            out.append("HDCP ligado/máximo: ").append(connectedHdcp).append(" / ").append(maxHdcp).append("\n");
            out.append("Nota: L1/L3 é reportado de forma mais direta pela propriedade Widevine securityLevel; ")
                    .append("os níveis HW_SECURE_* são a classificação genérica da API Android.\n");
        }
        out.append("Este teste não verifica certificação Netflix nem ESN Netflix.\n");

        String headline;
        if (!supported) {
            headline = "WIDEVINE: NÃO DETETADO";
        } else if (propSecurity.toUpperCase(Locale.ROOT).contains("L1")) {
            headline = "WIDEVINE: L1";
        } else if (propSecurity.toUpperCase(Locale.ROOT).contains("L3")) {
            headline = "WIDEVINE: L3";
        } else {
            headline = "WIDEVINE: PRESENTE — nível por confirmar";
        }

        String summary = headline +
                "\nSessão: " + sessionSecurity +
                "\nHDCP: " + connectedHdcp + " / máx. " + maxHdcp +
                "\nRelatório: Download/" + REPORT_NAME;

        return new ProbeResult(summary, out.toString());
    }

    private String safeProperty(MediaDrm drm, String name) {
        try {
            String value = drm.getPropertyString(name);
            return value == null || value.trim().isEmpty() ? "(vazio)" : value;
        } catch (Throwable t) {
            return "(não disponível: " + shortError(t) + ")";
        }
    }

    private String securityLevelName(int level) {
        switch (level) {
            case MediaDrm.SECURITY_LEVEL_SW_SECURE_CRYPTO: return "SW_SECURE_CRYPTO";
            case MediaDrm.SECURITY_LEVEL_SW_SECURE_DECODE: return "SW_SECURE_DECODE";
            case MediaDrm.SECURITY_LEVEL_HW_SECURE_CRYPTO: return "HW_SECURE_CRYPTO";
            case MediaDrm.SECURITY_LEVEL_HW_SECURE_DECODE: return "HW_SECURE_DECODE";
            case MediaDrm.SECURITY_LEVEL_HW_SECURE_ALL: return "HW_SECURE_ALL";
            case MediaDrm.SECURITY_LEVEL_UNKNOWN:
            default: return "UNKNOWN";
        }
    }

    private String hdcpLevelName(int level) {
        switch (level) {
            case MediaDrm.HDCP_NONE: return "NONE";
            case MediaDrm.HDCP_V1: return "HDCP 1.x";
            case MediaDrm.HDCP_V2: return "HDCP 2.0";
            case MediaDrm.HDCP_V2_1: return "HDCP 2.1";
            case MediaDrm.HDCP_V2_2: return "HDCP 2.2";
            case MediaDrm.HDCP_V2_3: return "HDCP 2.3";
            case MediaDrm.HDCP_NO_DIGITAL_OUTPUT: return "NO_DIGITAL_OUTPUT";
            case MediaDrm.HDCP_LEVEL_UNKNOWN:
            default: return "UNKNOWN";
        }
    }

    private void saveReport(String report, boolean showToast) {
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                ContentResolver resolver = getContentResolver();
                try {
                    resolver.delete(
                            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                            MediaStore.MediaColumns.DISPLAY_NAME + "=?",
                            new String[]{REPORT_NAME}
                    );
                } catch (Throwable ignored) {}

                ContentValues values = new ContentValues();
                values.put(MediaStore.MediaColumns.DISPLAY_NAME, REPORT_NAME);
                values.put(MediaStore.MediaColumns.MIME_TYPE, "text/plain");
                values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                values.put(MediaStore.MediaColumns.IS_PENDING, 1);

                Uri uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                if (uri == null) throw new IllegalStateException("MediaStore não devolveu URI.");

                try (OutputStream os = resolver.openOutputStream(uri, "w")) {
                    if (os == null) throw new IllegalStateException("Não foi possível abrir o ficheiro.");
                    os.write(report.getBytes(StandardCharsets.UTF_8));
                }

                ContentValues done = new ContentValues();
                done.put(MediaStore.MediaColumns.IS_PENDING, 0);
                resolver.update(uri, done, null, null);
            } else {
                File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                if (!dir.exists()) dir.mkdirs();
                File file = new File(dir, REPORT_NAME);
                try (FileOutputStream fos = new FileOutputStream(file, false)) {
                    fos.write(report.getBytes(StandardCharsets.UTF_8));
                }
            }

            if (showToast) runOnUiThread(() -> toast("Relatório guardado em Download/" + REPORT_NAME));
        } catch (Throwable t) {
            if (showToast) runOnUiThread(() -> toast("Erro ao guardar: " + shortError(t)));
        }
    }

    private String shortError(Throwable t) {
        String name = t.getClass().getSimpleName();
        String msg = t.getMessage();
        return msg == null || msg.trim().isEmpty() ? name : name + ": " + msg;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density);
    }

    private static class ProbeResult {
        final String summary;
        final String report;

        ProbeResult(String summary, String report) {
            this.summary = summary;
            this.report = report;
        }
    }
}
