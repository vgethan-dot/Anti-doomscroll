package ch.ethan.antiscroll

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.security.SecureRandom
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** Code de déblocage : PBKDF2-SHA256, mêmes réglages que le PC et l'extension. */
object Crypto {
    const val ITER = 150_000

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    private fun unhex(s: String) = ByteArray(s.length / 2) { s.substring(it * 2, it * 2 + 2).toInt(16).toByte() }

    private fun derive(code: String, salt: ByteArray, iter: Int): String {
        val spec = PBEKeySpec(code.toCharArray(), salt, iter, 256)
        val f = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        return hex(f.generateSecret(spec).encoded)
    }

    fun make(code: String): JSONObject {
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        return JSONObject().put("salt", hex(salt)).put("hash", derive(code, salt, ITER)).put("iter", ITER)
    }

    fun check(code: String, rec: JSONObject?): Boolean {
        if (rec == null) return true
        val h = derive(code, unhex(rec.getString("salt")), rec.optInt("iter", ITER))
        return h == rec.getString("hash")
    }
}

data class Objective(val id: String, val title: String, val start: String, val duration: Int, val days: List<Int>) {
    fun toJson(): JSONObject = JSONObject().put("id", id).put("title", title).put("start", start)
        .put("duration", duration).put("days", JSONArray(days))

    /** Occurrences (début, fin, clé) d'hier, aujourd'hui et demain. 0 = lundi ... 6 = dimanche */
    fun occurrences(now: LocalDateTime): List<Triple<LocalDateTime, LocalDateTime, String>> {
        val (h, m) = start.split(":").map { it.trim().toInt() }
        val out = mutableListOf<Triple<LocalDateTime, LocalDateTime, String>>()
        for (delta in -1L..1L) {
            val day: LocalDate = now.toLocalDate().plusDays(delta)
            if (days.isNotEmpty() && (day.dayOfWeek.value - 1) !in days) continue
            val s = LocalDateTime.of(day, LocalTime.of(h, m))
            out.add(Triple(s, s.plusMinutes(duration.toLong()), "$id@$day"))
        }
        return out
    }

    companion object {
        fun fromJson(o: JSONObject): Objective {
            val d = o.optJSONArray("days") ?: JSONArray()
            return Objective(o.getString("id"), o.optString("title", "Objectif"), o.getString("start"),
                o.getInt("duration"), (0 until d.length()).map { d.getInt(it) })
        }
    }
}

/** Les apps surveillées : nom affiché -> packages Android */
val TARGET_APPS = linkedMapOf(
    "TikTok" to listOf("com.zhiliaoapp.musically", "com.ss.android.ugc.trill"),
    "Instagram (Reels)" to listOf("com.instagram.android"),
    "YouTube (Shorts)" to listOf("com.google.android.youtube"),
    "Snapchat (Spotlight)" to listOf("com.snapchat.android"),
    "Facebook (Reels)" to listOf("com.facebook.katana"),
)

class Store(ctx: Context) {
    private val p = ctx.getSharedPreferences("antiscroll", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = p.getString("server_url", "") ?: ""
        set(v) = p.edit().putString("server_url", v).apply()
    var token: String
        get() = p.getString("token", "") ?: ""
        set(v) = p.edit().putString("token", v).apply()
    var username: String
        get() = p.getString("username", "") ?: ""
        set(v) = p.edit().putString("username", v).apply()

    var disabledApps: Set<String>
        get() = p.getStringSet("disabled_apps", emptySet()) ?: emptySet()
        set(v) = p.edit().putStringSet("disabled_apps", v).apply()

    var config: JSONObject
        get() = try {
            JSONObject(p.getString("config", null) ?: "")
        } catch (e: Exception) {
            JSONObject().put("updated_at", 0L).put("objectives", JSONArray())
                .put("settings", JSONObject().put("app_recheck_min", 3))
        }
        set(v) = p.edit().putString("config", v.toString()).apply()

    /** Modifie la config localement et la marque comme plus récente. */
    fun edit(block: (JSONObject) -> Unit) {
        val c = config
        block(c)
        c.put("updated_at", System.currentTimeMillis())
        config = c
    }

    fun unlockRec(): JSONObject? = config.optJSONObject("unlock")

    fun objectives(): List<Objective> {
        val a = config.optJSONArray("objectives") ?: return emptyList()
        return (0 until a.length()).mapNotNull { runCatching { Objective.fromJson(a.getJSONObject(it)) }.getOrNull() }
    }

    fun setObjectives(list: List<Objective>) = edit { c ->
        c.put("objectives", JSONArray().also { arr -> list.forEach { arr.put(it.toJson()) } })
    }

    fun activeBlock(now: LocalDateTime): Triple<Objective, LocalDateTime, String>? {
        for (o in objectives()) for ((s, e, k) in o.occurrences(now))
            if (!now.isBefore(s) && now.isBefore(e)) return Triple(o, e, k)
        return null
    }

    fun upcoming(now: LocalDateTime, withinMin: Long = 10): List<Triple<Objective, Long, String>> {
        val res = mutableListOf<Triple<Objective, Long, String>>()
        for (o in objectives()) for ((s, _, k) in o.occurrences(now)) {
            val sec = java.time.Duration.between(now, s).seconds
            if (sec in 1..withinMin * 60) res.add(Triple(o, sec, k))
        }
        return res
    }
}
