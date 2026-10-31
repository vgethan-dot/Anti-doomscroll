package ch.ethan.antiscroll

import android.accessibilityservice.AccessibilityService
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Rect
import android.media.AudioManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.concurrent.thread
import kotlin.math.abs
import kotlin.math.ceil

/**
 * Service d'accessibilité :
 *  - repère chaque nouvelle vidéo dans les fils de vidéos courtes -> écran noir + code
 *  - écran noir pendant les objectifs (alertes 10/5/1 min avant)
 * L'écran noir est une simple fenêtre par-dessus : rien n'est arrêté derrière.
 */
class GuardService : AccessibilityService() {

    private lateinit var store: Store
    private lateinit var api: Api
    private val ui = Handler(Looper.getMainLooper())
    private var wm: WindowManager? = null

    private var overlay: View? = null
    private var overlayKind = ""
    private var countdownView: TextView? = null
    private var countdownEnd: LocalDateTime? = null

    private val lastIndex = HashMap<String, Int>()   // dernière vidéo vue par app
    private var lastTrigger = 0L
    private var lastPkg = ""
    private val warned = HashSet<String>()
    private val unlockedBlocks = HashSet<String>()
    private var emergencyUntil = 0L
    private val emergencyUses = HashMap<String, Int>()
    private var lastSync = 0L
    private var appOkUntil = 0L                       // TikTok autorisé jusqu'à...

    override fun onServiceConnected() {
        store = Store(this)
        api = Api(store)
        wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("warn", "Alertes objectifs",
            NotificationManager.IMPORTANCE_HIGH))
        ui.post(tick)
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        hideOverlay()
        super.onDestroy()
    }

    // --------------------------- détection vidéos --------------------------- //
    private fun watchedPackages(): Set<String> {
        val off = store.disabledApps
        return TARGET_APPS.filterKeys { it !in off }.values.flatten().toSet()
    }

    override fun onAccessibilityEvent(e: AccessibilityEvent?) {
        if (e == null) return
        val pkg = e.packageName?.toString() ?: return
        if (pkg == packageName || pkg == "com.android.systemui" ||
            pkg.contains("inputmethod") || pkg.contains("keyboard")) return

        if (e.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            // Ouvrir TikTok (qui n'est qu'un fil de vidéos) demande le code tout de suite
            val tiktok = TARGET_APPS["TikTok"]!!
            if (pkg in tiktok && lastPkg !in tiktok && pkg in watchedPackages()
                && System.currentTimeMillis() > appOkUntil) {
                askForVideo(pkg, "Ouvrir TikTok ?")
            }
            lastPkg = pkg
            return
        }

        if (e.eventType != AccessibilityEvent.TYPE_VIEW_SCROLLED) return
        if (pkg !in watchedPackages() || overlay != null) return

        val src = e.source ?: return
        val screen = resources.displayMetrics
        val r = Rect()
        src.getBoundsInScreen(r)
        // Un fil de vidéos courtes = une liste plein écran dont chaque élément fait tout l'écran
        if (r.height() < screen.heightPixels * 0.7 || r.width() < screen.widthPixels * 0.8) return
        if (src.childCount > 0) {
            val child = src.getChild(0)
            if (child != null) {
                val cr = Rect()
                child.getBoundsInScreen(cr)
                if (cr.height() < screen.heightPixels * 0.6) return
            }
        }

        val idx = e.fromIndex
        val now = System.currentTimeMillis()
        if (idx >= 0) {
            val prev = lastIndex[pkg]
            lastIndex[pkg] = idx
            if (prev == null || prev == idx) return
        } else {
            // Pas d'index : on se base sur un grand défilement vertical
            val dy = if (Build.VERSION.SDK_INT >= 28) abs(e.scrollDeltaY) else 0
            if (dy < screen.heightPixels * 0.3 || now - lastTrigger < 1500) return
        }
        lastTrigger = now
        askForVideo(pkg, "Encore une vidéo ?")
    }

    private fun askForVideo(pkg: String, title: String) {
        pauseMedia()
        showOverlay("video", title, "Tape ton code pour voir cette vidéo.\nIl sera redemandé à la suivante.",
            onUnlock = {
                if (pkg in TARGET_APPS["TikTok"]!!) appOkUntil = System.currentTimeMillis() + 3000
                playMedia()
            },
            leaveLabel = "Partir", onLeave = { performGlobalAction(GLOBAL_ACTION_HOME) })
    }

    private fun mediaKey(code: Int) {
        val am = getSystemService(AudioManager::class.java)
        am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, code))
        am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, code))
    }
    private fun pauseMedia() = mediaKey(KeyEvent.KEYCODE_MEDIA_PAUSE)
    private fun playMedia() = mediaKey(KeyEvent.KEYCODE_MEDIA_PLAY)

    // ------------------------------- objectifs ------------------------------ //
    private val tick = object : Runnable {
        override fun run() {
            try { checkObjectives() } catch (_: Exception) {}
            if (store.token.isNotEmpty() && System.currentTimeMillis() - lastSync > 5 * 60_000) {
                lastSync = System.currentTimeMillis()
                thread { runCatching { api.sync() } }
            }
            ui.postDelayed(this, 10_000)
        }
    }

    private fun checkObjectives() {
        val now = LocalDateTime.now()
        for ((o, sec, key) in store.upcoming(now)) {
            val crossed = listOf(10, 5, 1).filter { sec <= it * 60 }
            if (crossed.any { "$key#$it" !in warned }) {
                crossed.forEach { warned.add("$key#$it") }
                val mins = maxOf(1, ceil(sec / 60.0).toInt())
                notify("« ${o.title} » dans $mins min",
                    "Ton téléphone sera bloqué pendant ${o.duration} min.")
            }
        }
        val blk = store.activeBlock(now)
        if (blk != null && blk.third !in unlockedBlocks && System.currentTimeMillis() > emergencyUntil) {
            val (o, end, key) = blk
            if (overlayKind != "block") {
                hideOverlay()
                val used = emergencyUses[key] ?: 0
                showOverlay("block", "🎯 ${o.title}",
                    "Bloqué jusqu'à ${end.format(DateTimeFormatter.ofPattern("HH:mm"))}.\nTes apps tournent toujours derrière.",
                    onUnlock = { unlockedBlocks.add(key) },
                    leaveLabel = if (used < 3) "Urgence : 2 min (${3 - used} restantes)" else null,
                    onLeave = {
                        emergencyUses[key] = used + 1
                        emergencyUntil = System.currentTimeMillis() + 2 * 60_000
                    },
                    countdown = end)
            }
        } else if (overlayKind == "block" && (blk == null || blk.third in unlockedBlocks)) {
            hideOverlay()
        }
    }

    private fun notify(title: String, text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        val n = Notification.Builder(this, "warn")
            .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(title).setContentText(text).setAutoCancel(true).build()
        nm.notify(title.hashCode(), n)
    }

    // ------------------------------ écran noir ------------------------------ //
    private fun showOverlay(kind: String, title: String, subtitle: String, onUnlock: () -> Unit,
                            leaveLabel: String?, onLeave: () -> Unit, countdown: LocalDateTime? = null) {
        if (overlay != null) return
        val w = wm ?: return
        val dp = resources.displayMetrics.density
        fun px(v: Int) = (v * dp).toInt()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            setPadding(px(28), px(28), px(28), px(28))
            isClickable = true
        }
        fun label(t: String, size: Float, color: Int) = TextView(this).apply {
            text = t; textSize = size; setTextColor(color); gravity = Gravity.CENTER
            setPadding(0, px(6), 0, px(6))
        }
        root.addView(label(title, 26f, Color.WHITE))
        root.addView(label(subtitle, 15f, Color.GRAY))
        countdownView = if (countdown != null) label("", 20f, Color.rgb(127, 178, 255)).also { root.addView(it) } else null
        countdownEnd = countdown

        val hasCode = store.unlockRec() != null
        val input = EditText(this).apply {
            hint = "Code"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setTextColor(Color.WHITE); setHintTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
        }
        val msg = label("", 14f, Color.rgb(255, 107, 107))
        if (hasCode) root.addView(input, LinearLayout.LayoutParams(px(240), LinearLayout.LayoutParams.WRAP_CONTENT))
        else root.addView(label("Aucun code choisi : ouvre l'app AntiScroll", 14f, Color.LTGRAY))

        val unlock = Button(this).apply { text = if (hasCode) "Débloquer" else "Continuer" }
        unlock.setOnClickListener {
            val code = input.text.toString()
            input.setText("")
            unlock.isEnabled = false
            thread {
                val ok = runCatching { Crypto.check(code, store.unlockRec()) }.getOrDefault(false)
                ui.post {
                    unlock.isEnabled = true
                    if (ok) { hideOverlay(); onUnlock() } else msg.text = "Code incorrect"
                }
            }
        }
        root.addView(unlock)
        if (leaveLabel != null) {
            root.addView(Button(this).apply {
                text = leaveLabel
                setOnClickListener { hideOverlay(); onLeave() }
            })
        }
        root.addView(msg)

        val lp = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.OPAQUE
        ).apply { softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE }

        try {
            w.addView(root, lp)
            overlay = root
            overlayKind = kind
            if (countdown != null) ui.post(countdownTick)
        } catch (_: Exception) {}
    }

    private val countdownTick = object : Runnable {
        override fun run() {
            val end = countdownEnd ?: return
            val tv = countdownView ?: return
            val left = java.time.Duration.between(LocalDateTime.now(), end).seconds
            if (left <= 0) { hideOverlay(); return }
            tv.text = "Fin dans %02d:%02d".format(left / 60, left % 60)
            ui.postDelayed(this, 1000)
        }
    }

    private fun hideOverlay() {
        ui.removeCallbacks(countdownTick)
        overlay?.let { runCatching { wm?.removeView(it) } }
        overlay = null
        overlayKind = ""
        countdownView = null
        countdownEnd = null
    }
}
