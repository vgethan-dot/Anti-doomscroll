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

/** Tout est stocké sur le téléphone (aucun serveur). */
class Store(ctx: Context) {
    private val p = ctx.getSharedPreferences("antiscroll", Context.MODE_PRIVATE)

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

class ConfigFileException(msg: String) : Exception(msg)

/**
 * Export / import de la config dans un fichier .json, pour la copier sur un
 * autre appareil (même format que l'app PC). Le code n'est jamais écrit en
 * clair : seulement son empreinte (sel + hash).
 */
object ConfigFile {
    private const val APP = "antiscroll"
    private const val VERSION = 1

    fun export(store: Store): String {
        val c = store.config
        val cfg = JSONObject()
            .put("unlock", c.optJSONObject("unlock") ?: JSONObject.NULL)
            .put("objectives", c.optJSONArray("objectives") ?: JSONArray())
            .put("settings", c.optJSONObject("settings") ?: JSONObject().put("app_recheck_min", 3))
        return JSONObject()
            .put("app", APP).put("version", VERSION)
            .put("exported_at", System.currentTimeMillis())
            .put("config", cfg)
            .put("android_disabled_apps", JSONArray(store.disabledApps.toList()))
            .toString(2)
    }

    /** Vérifie le fichier. Renvoie (config, apps désactivées ou null). */
    fun parse(text: String): Pair<JSONObject, Set<String>?> {
        val data = runCatching { JSONObject(text) }.getOrNull()
        if (data == null || data.optString("app") != APP) throw ConfigFileException("Ce fichier n'est pas une config AntiScroll")
        if (data.optInt("version", 0) > VERSION) throw ConfigFileException("Config créée par une version plus récente d'AntiScroll")
        val cfg = data.optJSONObject("config") ?: throw ConfigFileException("Config vide ou abîmée")

        val objs = JSONArray()
        val arr = cfg.optJSONArray("objectives") ?: JSONArray()
        for (i in 0 until arr.length()) {
            val o = try {
                val j = arr.getJSONObject(i)
                val (h, m) = j.getString("start").split(":").map { it.trim().toInt() }
                require(h in 0..23 && m in 0..59)
                val dur = j.getInt("duration")
                require(dur in 1..1440)
                val d = j.optJSONArray("days") ?: JSONArray()
                val days = (0 until d.length()).map { d.getInt(it) }.filter { it in 0..6 }.distinct().sorted()
                Objective(j.optString("id").ifBlank { java.util.UUID.randomUUID().toString().take(12) },
                    j.optString("title").ifBlank { "Objectif" }, "%02d:%02d".format(h, m), dur, days)
            } catch (e: Exception) {
                throw ConfigFileException("Un objectif du fichier est abîmé")
            }
            objs.put(o.toJson())
        }

        val unlock = cfg.optJSONObject("unlock")?.let { u ->
            try {
                val salt = u.getString("salt"); val hash = u.getString("hash")
                val iter = u.optInt("iter", Crypto.ITER)
                require(salt.matches(Regex("[0-9a-fA-F]+")) && salt.length % 2 == 0)
                require(hash.matches(Regex("[0-9a-fA-F]{64}")))
                require(iter >= 1000)
                JSONObject().put("salt", salt).put("hash", hash).put("iter", iter)
            } catch (e: Exception) {
                throw ConfigFileException("Code invalide dans le fichier")
            }
        }
        val recheck = (cfg.optJSONObject("settings")?.optInt("app_recheck_min", 3) ?: 3).coerceIn(1, 120)

        val config = JSONObject()
            .put("updated_at", System.currentTimeMillis())
            .put("unlock", unlock ?: JSONObject.NULL)
            .put("objectives", objs)
            .put("settings", JSONObject().put("app_recheck_min", recheck))
        val disabled = data.optJSONArray("android_disabled_apps")?.let { a ->
            (0 until a.length()).map { a.getString(it) }.filter { it in TARGET_APPS.keys }.toSet()
        }
        return config to disabled
    }
}
