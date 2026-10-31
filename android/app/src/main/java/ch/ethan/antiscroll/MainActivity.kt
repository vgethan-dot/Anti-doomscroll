package ch.ethan.antiscroll

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.app.TimePickerDialog
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import java.util.UUID
import kotlin.concurrent.thread

class MainActivity : Activity() {

    private lateinit var store: Store
    private lateinit var api: Api
    private lateinit var content: LinearLayout
    private lateinit var cur: LinearLayout      // carte (section) en cours de remplissage
    private val days = listOf("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = Store(this)
        api = Api(store)
        window.statusBarColor = Ui.CYAN_DARK
        val page = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Ui.BG)
        }
        // Bandeau cyan en haut
        page.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Ui.CYAN)
            setPadding(px(22), px(26), px(22), px(26))
            addView(TextView(this@MainActivity).apply {
                text = "AntiScroll"; textSize = 30f; setTextColor(Color.WHITE)
                setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD))
            })
            addView(TextView(this@MainActivity).apply {
                text = "Moins de scroll, plus de temps pour toi."
                textSize = 15f; setTextColor(Color.rgb(230, 251, 255))
            })
        })
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(px(14), px(4), px(14), px(40))
        }
        cur = content
        page.addView(content)
        setContentView(ScrollView(this).apply { setBackgroundColor(Ui.BG); addView(page) })
        if (Build.VERSION.SDK_INT >= 33) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    override fun onResume() {
        super.onResume()
        build()
        if (store.token.isNotEmpty()) bg({ api.sync() }) { if (it == null) build() }
    }

    // ------------------------------ helpers -------------------------------- //
    private fun px(v: Int) = (v * resources.displayMetrics.density).toInt()

    /** Nouvelle carte blanche avec un titre ; les éléments suivants s'y ajoutent. */
    private fun section(t: String) {
        cur = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = Ui.rounded(this@MainActivity, Ui.CARD, 18, Ui.BORDER)
            setPadding(px(18), px(16), px(18), px(18))
            elevation = px(1).toFloat()
        }
        content.addView(cur, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = px(14) })
        cur.addView(TextView(this).apply {
            text = t; textSize = 19f; setTextColor(Ui.TEXT)
            setTypeface(Typeface.create("sans-serif-medium", Typeface.BOLD))
            setPadding(0, 0, 0, px(8))
        })
    }

    private fun text(t: String, color: Int = Ui.MUTED, parent: LinearLayout = cur) =
        TextView(this).apply {
            text = t; setTextColor(color); textSize = 15f; setLineSpacing(0f, 1.15f)
            setPadding(0, px(2), 0, px(2))
        }.also { parent.addView(it) }

    private fun button(t: String, parent: LinearLayout = cur, kind: Ui.Kind = Ui.Kind.PRIMARY,
                       onClick: () -> Unit) =
        Button(this).apply {
            text = t; setOnClickListener { onClick() }
            Ui.styleButton(this, kind)
        }.also {
            val horizontal = parent.orientation == LinearLayout.HORIZONTAL
            parent.addView(it, LinearLayout.LayoutParams(
                if (horizontal) LinearLayout.LayoutParams.WRAP_CONTENT else LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = px(8)
                if (horizontal) marginEnd = px(8)
            })
        }

    private fun field(hint: String, password: Boolean = false, number: Boolean = false) = EditText(this).apply {
        this.hint = hint
        inputType = when {
            password -> InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            number -> InputType.TYPE_CLASS_NUMBER
            else -> InputType.TYPE_CLASS_TEXT
        }
        Ui.styleField(this)
    }.also {
        cur.addView(it, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply { topMargin = px(8) })
    }

    private fun checkBox(t: String) = CheckBox(this).apply {
        text = t; setTextColor(Ui.TEXT); textSize = 15f
        buttonTintList = ColorStateList.valueOf(Ui.CYAN)
    }

    private fun row(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.HORIZONTAL
        gravity = Gravity.CENTER_VERTICAL
    }.also { cur.addView(it) }

    private fun toast(t: String) = Toast.makeText(this, t, Toast.LENGTH_LONG).show()

    /** Lance une tâche réseau en arrière-plan ; done(null) = succès, sinon message d'erreur. */
    private fun bg(work: () -> Unit, done: (String?) -> Unit) {
        thread {
            val err = try { work(); null } catch (e: ApiException) { e.message ?: "Erreur" } catch (e: Exception) { "Erreur : ${e.message}" }
            runOnUiThread { done(err) }
        }
    }

    private fun askText(title: String, hint: String, password: Boolean, onText: (String) -> Unit) {
        val input = EditText(this).apply {
            this.hint = hint
            inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                        else InputType.TYPE_CLASS_TEXT
            Ui.styleField(this)
        }
        val box = LinearLayout(this).apply {
            setPadding(px(22), px(8), px(22), 0)
            addView(input, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        AlertDialog.Builder(this).setTitle(title).setView(box)
            .setPositiveButton("OK") { _, _ -> onText(input.text.toString()) }
            .setNegativeButton("Annuler", null).show()
    }

    /** Demande le code (s'il existe) avant une action sensible. */
    private fun withCode(why: String, onOk: () -> Unit) {
        val rec = store.unlockRec() ?: return onOk()
        askText(why, "Code", true) { code ->
            thread {
                val ok = Crypto.check(code, rec)
                runOnUiThread { if (ok) onOk() else toast("Code incorrect") }
            }
        }
    }

    private fun syncBg() {
        if (store.token.isNotEmpty()) bg({ api.sync() }) { }
    }

    private fun serviceEnabled(): Boolean {
        val s = Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES) ?: ""
        return s.contains("$packageName/")
    }

    // ------------------------------- écran --------------------------------- //
    private fun build() {
        content.removeAllViews()
        cur = content

        // Statut
        section("Protection")
        if (serviceEnabled()) {
            text("Service actif ✔", Ui.GREEN)
        } else {
            text("Service désactivé ✖\nActive « AntiScroll » dans Accessibilité. Si Android bloque " +
                 "(« paramètre restreint ») : Infos de l'appli → ⋮ → Autoriser les paramètres restreints.",
                 Ui.RED)
            button("Ouvrir les réglages d'accessibilité") {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }

        // Code
        section("Code de déblocage")
        text(if (store.unlockRec() != null) "Code défini ✔" else "Pas encore de code : choisis-en un !",
             if (store.unlockRec() != null) Ui.GREEN else Ui.MUTED)
        button("Choisir / changer le code") {
            withCode("Code actuel") {
                askText("Nouveau code", "4 caractères minimum", true) { c1 ->
                    if (c1.length < 4) return@askText toast("4 caractères minimum")
                    askText("Répète le code", "Code", true) { c2 ->
                        if (c1 != c2) return@askText toast("Les codes ne correspondent pas")
                        thread {
                            val rec = Crypto.make(c1)
                            runOnUiThread {
                                store.edit { it.put("unlock", rec) }
                                syncBg(); build(); toast("Code enregistré ✔")
                            }
                        }
                    }
                }
            }
        }

        // Objectifs
        section("Objectifs")
        val objs = store.objectives()
        if (objs.isEmpty()) text("Aucun objectif pour l'instant.")
        for (o in objs) {
            val r = row()
            val d = if (o.days.isEmpty()) "tous les jours" else o.days.joinToString(", ") { days[it] }
            r.background = Ui.rounded(this, Ui.CYAN_SOFT, 12)
            r.setPadding(px(14), px(4), px(6), px(10))
            (r.layoutParams as LinearLayout.LayoutParams).topMargin = px(8)
            text("${o.start} • ${o.duration} min • ${o.title}\n$d", Ui.TEXT, r).apply {
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            }
            button("✕", r, Ui.Kind.DANGER) {
                withCode("Code pour supprimer « ${o.title} »") {
                    store.setObjectives(store.objectives().filter { it.id != o.id })
                    syncBg(); build()
                }
            }
        }
        text("\nNouvel objectif", Ui.TEXT).setTypeface(null, Typeface.BOLD)
        val title = field("Objectif (ex. Réviser les maths)")
        var start = "18:00"
        val timeBtn = button("Heure : $start", kind = Ui.Kind.SECONDARY) {}
        timeBtn.setOnClickListener {
            val (h, m) = start.split(":").map { it.toInt() }
            TimePickerDialog(this, { _, hh, mm ->
                start = "%02d:%02d".format(hh, mm); timeBtn.text = "Heure : $start"
            }, h, m, true).show()
        }
        val dur = field("Durée en minutes", number = true)
        text("Jours (aucun coché = tous les jours) :")
        val dayRow = LinearLayout(this)
        cur.addView(HorizontalScrollView(this).apply { addView(dayRow) })
        val checks = days.map { d -> checkBox(d).also { dayRow.addView(it) } }
        button("Ajouter l'objectif") {
            val minutes = dur.text.toString().toIntOrNull() ?: 0
            if (minutes !in 1..1440) return@button toast("Durée entre 1 et 1440 minutes")
            val o = Objective(UUID.randomUUID().toString().take(12),
                title.text.toString().ifBlank { "Objectif" }, start, minutes,
                checks.indices.filter { checks[it].isChecked })
            store.setObjectives(store.objectives() + o)
            syncBg(); build(); toast("Objectif ajouté ✔ (alertes 10, 5 et 1 min avant)")
        }

        // Apps surveillées
        section("Apps surveillées")
        for (name in TARGET_APPS.keys) {
            val cb = checkBox(name).apply { isChecked = name !in store.disabledApps }
            cb.setOnCheckedChangeListener { box, checked ->
                if (checked) {
                    store.disabledApps = store.disabledApps - name
                } else {
                    box.isChecked = true   // remis tant que le code n'est pas bon
                    withCode("Code pour ne plus surveiller $name") {
                        store.disabledApps = store.disabledApps + name
                        build()
                    }
                }
            }
            cur.addView(cb)
        }

        // Compte
        section("Compte")
        val srv = field("Serveur (ex. http://100.x.y.z:47800)")
        srv.setText(store.serverUrl)
        fun saveSrv() {
            var u = srv.text.toString().trim().trimEnd('/')
            if (u.isNotEmpty() && !u.startsWith("http")) u = "http://$u"
            store.serverUrl = u
        }
        if (store.token.isNotEmpty()) {
            text("Connecté : ${store.username}", Ui.TEXT).setTypeface(null, Typeface.BOLD)
            button("Synchroniser") { saveSrv(); bg({ api.sync() }) { toast(it ?: "Synchronisé ✔"); build() } }
            button("Changer de pseudo", kind = Ui.Kind.SECONDARY) {
                askText("Nouveau pseudo", "Pseudo", false) { n ->
                    saveSrv(); bg({ api.changeUsername(n) }) { toast(it ?: "Pseudo changé ✔"); build() }
                }
            }
            button("Changer le mot de passe", kind = Ui.Kind.SECONDARY) {
                askText("Mot de passe actuel", "Actuel", true) { old ->
                    askText("Nouveau mot de passe", "6 caractères min.", true) { new ->
                        bg({ api.changePassword(old, new) }) { toast(it ?: "Mot de passe changé ✔") }
                    }
                }
            }
            button("Se déconnecter", kind = Ui.Kind.SECONDARY) { bg({ api.logout() }) { build() } }
            button("Supprimer le compte", kind = Ui.Kind.DANGER) {
                askText("Supprimer le compte (définitif)", "Mot de passe du compte", true) { pw ->
                    bg({ api.deleteAccount(pw) }) { toast(it ?: "Compte supprimé"); build() }
                }
            }
        } else {
            val u = field("Pseudo")
            val p = field("Mot de passe du compte", password = true)
            val r = row()
            button("Se connecter", r) {
                saveSrv(); bg({ api.login(u.text.toString(), p.text.toString()) }) { toast(it ?: "Connecté ✔"); build() }
            }
            button("Créer un compte", r, Ui.Kind.SECONDARY) {
                saveSrv(); bg({ api.register(u.text.toString(), p.text.toString()) }) { toast(it ?: "Compte créé ✔"); build() }
            }
            text("Sans compte, l'app marche quand même (sans synchro).", Ui.MUTED)
        }
        content.addView(View(this), LinearLayout.LayoutParams(1, px(40)))
    }
}
