package pt.horariosfamilia.r2adrmprobe;

import android.app.Activity;
import android.media.MediaDrm;
import android.os.Bundle;
import android.text.method.ScrollingMovementMethod;
import android.view.Gravity;
import android.widget.TextView;
import java.util.UUID;

public class MainActivity extends Activity {
    private static final UUID WIDEVINE = new UUID(0xedef8ba979d64aceL, 0xa3c827dcd51d21edL);

    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        TextView v = new TextView(this);
        v.setTextSize(22); v.setPadding(42,30,42,30); v.setGravity(Gravity.START);
        v.setMovementMethod(new ScrollingMovementMethod());
        v.setText(probe());
        setContentView(v);
    }

    private String prop(MediaDrm d, String key) {
        try {
            String s=d.getPropertyString(key);
            return (s==null || s.isEmpty()) ? "(vazio)" : s;
        } catch(Throwable t) { return "(não exposto: "+t.getClass().getSimpleName()+")"; }
    }

    private String probe() {
        StringBuilder s=new StringBuilder();
        s.append("R2A — SONDA DRM / WIDEVINE\n\n");
        s.append("Android: ").append(android.os.Build.VERSION.RELEASE).append(" (SDK ").append(android.os.Build.VERSION.SDK_INT).append(")\n");
        s.append("Fabricante: ").append(android.os.Build.MANUFACTURER).append("\n");
        s.append("Modelo: ").append(android.os.Build.MODEL).append("\n\n");
        boolean supported=false;
        try { supported=MediaDrm.isCryptoSchemeSupported(WIDEVINE); } catch(Throwable ignored){}
        s.append("Widevine suportado: ").append(supported ? "SIM" : "NÃO").append("\n");
        if(!supported) return s.toString();
        MediaDrm d=null;
        try {
            d=new MediaDrm(WIDEVINE);
            s.append("\n===== PROPRIEDADES WIDEVINE =====\n");
            String[] keys={"securityLevel","vendor","version","description","algorithms","systemId","privacyMode","sessionSharing","usageReportingSupport","appId","origin","hdcpLevel","maxHdcpLevel","maxNumberOfSessions","numberOfOpenSessions"};
            for(String k:keys) s.append(k).append(": ").append(prop(d,k)).append("\n");
            s.append("\n===== LEITURA RÁPIDA =====\n");
            String level=prop(d,"securityLevel");
            if(level.toUpperCase().contains("L1")) s.append("Widevine Security Level: L1\n");
            else if(level.toUpperCase().contains("L3")) s.append("Widevine Security Level: L3\n");
            else s.append("Widevine Security Level: não determinado automaticamente (valor: ").append(level).append(")\n");
            s.append("\nNota: Widevine L1 não prova certificação Netflix. Netflix exige também autorização/certificação própria do dispositivo e ESN compatível.\n");
        } catch(Throwable t) {
            s.append("\nERRO ao abrir Widevine: ").append(t.toString()).append("\n");
        } finally { if(d!=null) try { d.close(); } catch(Throwable ignored){} }
        return s.toString();
    }
}
