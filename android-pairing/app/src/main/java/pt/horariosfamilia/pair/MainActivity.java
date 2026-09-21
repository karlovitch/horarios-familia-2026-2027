package pt.horariosfamilia.pair;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.ComponentName;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final String WEB_URL =
        "https://karlovitch.github.io/horarios-familia-2026-2027/";
    private static final String TV_PACKAGE = "pt.horariosfamilia.tv";
    private static final String TV_ACTIVITY =
        "pt.horariosfamilia.tv.MainActivity";

    private EditText codeInput;
    private TextView statusText;
    private Button pairButton;
    private Button openButton;

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private TextView text(String value, float sp, boolean bold) {
        TextView v = new TextView(this);
        v.setText(value);
        v.setTextSize(sp);
        v.setTextColor(Color.rgb(15, 23, 42));
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return v;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestWindowFeature(Window.FEATURE_NO_TITLE);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(247, 248, 250));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(28), dp(28), dp(28), dp(28));

        TextView title = text("Emparelhar Agenda pessoal", 26, true);
        title.setGravity(Gravity.CENTER);
        root.addView(title, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView subtitle = text(
            "Horários Família · Carlos + Sandrinha\n\n" +
            "Introduz o código da Agenda pessoal neste dispositivo. " +
            "A chave não fica incorporada nesta APK.", 16, false);
        subtitle.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams subtitleLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT);
        subtitleLp.topMargin = dp(14);
        root.addView(subtitle, subtitleLp);

        codeInput = new EditText(this);
        codeInput.setSingleLine(true);
        codeInput.setHint("Código da Agenda pessoal");
        codeInput.setTextSize(18);
        codeInput.setInputType(
            InputType.TYPE_CLASS_TEXT |
            InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        codeInput.setPadding(dp(14), dp(14), dp(14), dp(14));
        codeInput.setSelectAllOnFocus(true);
        codeInput.setFocusable(true);
        codeInput.setFocusableInTouchMode(true);
        LinearLayout.LayoutParams inputLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT);
        inputLp.topMargin = dp(24);
        root.addView(codeInput, inputLp);

        pairButton = new Button(this);
        pairButton.setText("Emparelhar este dispositivo");
        pairButton.setTextSize(17);
        pairButton.setAllCaps(false);
        pairButton.setFocusable(true);
        pairButton.setOnClickListener(v -> pairDevice());
        LinearLayout.LayoutParams btnLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(58));
        btnLp.topMargin = dp(18);
        root.addView(pairButton, btnLp);

        openButton = new Button(this);
        openButton.setText("Abrir Horários Família");
        openButton.setTextSize(16);
        openButton.setAllCaps(false);
        openButton.setFocusable(true);
        openButton.setVisibility(View.GONE);
        openButton.setOnClickListener(v -> openHorariosFamilia());
        LinearLayout.LayoutParams openLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(54));
        openLp.topMargin = dp(10);
        root.addView(openButton, openLp);

        statusText = text(
            "Em Android TV, a APK tenta emparelhar diretamente a app Horários Família. " +
            "Num telemóvel ou tablet, abre a ligação segura de emparelhamento no browser/PWA.",
            14, false);
        statusText.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams statusLp = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT);
        statusLp.topMargin = dp(20);
        root.addView(statusText, statusLp);

        scroll.addView(root);
        setContentView(scroll);

        codeInput.requestFocus();
    }

    private void pairDevice() {
        String key = codeInput.getText() == null
            ? ""
            : codeInput.getText().toString().trim();

        if (key.length() < 20) {
            showError("O código parece demasiado curto. Confirma o código da Agenda pessoal.");
            codeInput.requestFocus();
            return;
        }

        if (sendKeyToNativeApp(key)) {
            codeInput.setText("");
            codeInput.setVisibility(View.GONE);
            pairButton.setVisibility(View.GONE);
            showSuccess("✅ Agenda ligada neste dispositivo");
            openButton.setVisibility(View.VISIBLE);
            openButton.requestFocus();
            return;
        }

        String pairUrl = WEB_URL + "#agendaKey=" + Uri.encode(key);
        if (openWeb(pairUrl)) {
            codeInput.setText("");
            showSuccess("✅ Emparelhamento enviado para este dispositivo");
            openButton.setVisibility(View.VISIBLE);
        } else {
            showError("Não encontrei a app Horários Família nem um browser capaz de abrir a ligação.");
        }
    }

    private boolean sendKeyToNativeApp(String key) {
        try {
            PackageManager pm = getPackageManager();
            pm.getPackageInfo(TV_PACKAGE, 0);

            Intent pairing = new Intent("pt.horariosfamilia.tv.PAIR_AGENDA");
            pairing.setComponent(new ComponentName(
                TV_PACKAGE,
                "pt.horariosfamilia.tv.AgendaPairingReceiver"));
            pairing.putExtra("agendaKey", key);
            sendBroadcast(pairing);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    private void openHorariosFamilia() {
        try {
            Intent launch = getPackageManager().getLaunchIntentForPackage(TV_PACKAGE);
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                startActivity(launch);
                return;
            }
        } catch (Exception ignored) {
        }
        openWeb(WEB_URL);
    }

    private void showSuccess(String message) {
        statusText.setText(message + "\n\nA chave ficou guardada localmente. Agora podes abrir Horários Família.");
        statusText.setTextColor(Color.rgb(22, 101, 52));
        statusText.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        statusText.setTextSize(18);
    }

    private void showError(String message) {
        statusText.setText("⚠ " + message);
        statusText.setTextColor(Color.rgb(153, 27, 27));
        statusText.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        statusText.setTextSize(16);
    }

    private boolean openWeb(String url) {
        try {
            Intent browser = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
            browser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(browser);
            return true;
        } catch (Exception ex) {
            return false;
        }
    }
}
