package pt.horariosfamilia.tv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

public class AgendaPairingReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !"pt.horariosfamilia.tv.PAIR_AGENDA".equals(intent.getAction())) {
            return;
        }

        String key = intent.getStringExtra("agendaKey");
        if (key == null) return;

        key = key.trim();
        if (key.length() < 20) return;

        SharedPreferences prefs = context.getSharedPreferences("tv", Context.MODE_PRIVATE);
        prefs.edit().putString("agendaKey", key).apply();
    }
}
