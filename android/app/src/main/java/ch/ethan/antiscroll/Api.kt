package ch.ethan.antiscroll

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ApiException(msg: String) : Exception(msg)

/** Client du serveur AntiScroll (à appeler hors du thread principal). */
class Api(private val store: Store) {

    private fun req(method: String, path: String, body: JSONObject? = null, auth: Boolean = true): JSONObject {
        val base = store.serverUrl.trimEnd('/')
        if (base.isEmpty()) throw ApiException("Adresse du serveur non configurée")
        val c = try {
            URL(base + path).openConnection() as HttpURLConnection
        } catch (e: Exception) {
            throw ApiException("Adresse invalide")
        }
        try {
            c.requestMethod = method
            c.connectTimeout = 6000
            c.readTimeout = 6000
            c.setRequestProperty("Content-Type", "application/json")
            if (auth && store.token.isNotEmpty()) c.setRequestProperty("Authorization", "Bearer ${store.token}")
            if (body != null) {
                c.doOutput = true
                c.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
            val json = runCatching { JSONObject(text) }.getOrElse { JSONObject() }
            if (code !in 200..299) throw ApiException(json.optString("error", "Erreur $code"))
            return json
        } catch (e: ApiException) {
            throw e
        } catch (e: Exception) {
            throw ApiException("Serveur injoignable (Tailscale activé ?)")
        } finally {
            c.disconnect()
        }
    }

    fun register(u: String, p: String) = loggedIn(req("POST", "/register",
        JSONObject().put("username", u).put("password", p), auth = false))

    fun login(u: String, p: String) = loggedIn(req("POST", "/login",
        JSONObject().put("username", u).put("password", p), auth = false))

    private fun loggedIn(r: JSONObject) {
        store.token = r.getString("token")
        store.username = r.getString("username")
        sync(preferServerIfEmpty = true)
    }

    fun logout() {
        runCatching { req("POST", "/logout", JSONObject()) }
        store.token = ""; store.username = ""
    }

    fun changePassword(old: String, new: String) {
        req("POST", "/account/password", JSONObject().put("old", old).put("new", new))
    }

    fun changeUsername(new: String) {
        store.username = req("POST", "/account/username", JSONObject().put("username", new)).getString("username")
    }

    fun deleteAccount(pw: String) {
        req("DELETE", "/account", JSONObject().put("password", pw))
        store.token = ""; store.username = ""
    }

    /** Le plus récent gagne (même logique que le PC). */
    fun sync(preferServerIfEmpty: Boolean = false): Boolean {
        if (store.token.isEmpty()) return false
        val remote = req("GET", "/config").getJSONObject("config")
        val local = store.config
        val rT = remote.optLong("updated_at", 0)
        val lT = local.optLong("updated_at", 0)
        val localEmpty = (local.optJSONArray("objectives")?.length() ?: 0) == 0 && local.optJSONObject("unlock") == null
        if (rT > lT || (preferServerIfEmpty && localEmpty && rT > 0)) {
            store.config = remote
        } else if (lT > rT) {
            store.config = req("PUT", "/config", JSONObject().put("config", local)).getJSONObject("config")
        }
        return true
    }
}
