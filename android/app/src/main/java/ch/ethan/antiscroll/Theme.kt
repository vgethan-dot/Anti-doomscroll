package ch.ethan.antiscroll

import android.content.Context
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.Drawable
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.RippleDrawable
import android.widget.Button
import android.widget.EditText

/** Thème moderne commun : blanc + bleu cyan. */
object Ui {
    val BG = Color.rgb(244, 249, 251)         // fond de l'écran
    val CARD = Color.WHITE                    // cartes
    val TEXT = Color.rgb(15, 23, 42)          // texte principal
    val MUTED = Color.rgb(100, 116, 139)      // texte secondaire
    val BORDER = Color.rgb(219, 231, 236)     // bordures
    val CYAN = Color.rgb(6, 182, 212)         // couleur principale
    val CYAN_DARK = Color.rgb(8, 145, 178)    // appui
    val CYAN_SOFT = Color.rgb(224, 247, 251)  // fond léger cyan
    val RED = Color.rgb(239, 68, 68)
    val RED_SOFT = Color.rgb(253, 236, 236)
    val GREEN = Color.rgb(16, 185, 129)

    enum class Kind { PRIMARY, SECONDARY, DANGER, GHOST }

    fun dp(ctx: Context, v: Int) = (v * ctx.resources.displayMetrics.density).toInt()

    fun rounded(ctx: Context, fill: Int, radiusDp: Int = 14, stroke: Int? = null, strokeDp: Int = 1) =
        GradientDrawable().apply {
            setColor(fill)
            cornerRadius = dp(ctx, radiusDp).toFloat()
            if (stroke != null) setStroke(dp(ctx, strokeDp), stroke)
        }

    private fun ripple(ctx: Context, fill: Int, press: Int, stroke: Int? = null): Drawable =
        RippleDrawable(ColorStateList.valueOf(press), rounded(ctx, fill, 12, stroke), null)

    /** Donne à un bouton le style du thème (arrondi, sans majuscules forcées). */
    fun styleButton(b: Button, kind: Kind = Kind.PRIMARY) {
        val ctx = b.context
        val (fill, text, press) = when (kind) {
            Kind.PRIMARY -> Triple(CYAN, Color.WHITE, CYAN_DARK)
            Kind.SECONDARY -> Triple(CYAN_SOFT, CYAN_DARK, Color.rgb(198, 238, 246))
            Kind.DANGER -> Triple(RED_SOFT, RED, Color.rgb(251, 213, 213))
            Kind.GHOST -> Triple(Color.TRANSPARENT, MUTED, CYAN_SOFT)
        }
        b.background = ripple(ctx, fill, press)
        b.setTextColor(text)
        b.isAllCaps = false
        b.textSize = 15f
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL))
        b.stateListAnimator = null
        b.minHeight = dp(ctx, 46)
        b.setPadding(dp(ctx, 18), dp(ctx, 10), dp(ctx, 18), dp(ctx, 10))
    }

    /** Champ de saisie arrondi, fond clair, bordure fine. */
    fun styleField(e: EditText) {
        val ctx = e.context
        e.background = rounded(ctx, BG, 12, BORDER)
        e.setTextColor(TEXT)
        e.setHintTextColor(MUTED)
        e.textSize = 16f
        e.setPadding(dp(ctx, 14), dp(ctx, 12), dp(ctx, 14), dp(ctx, 12))
    }
}
