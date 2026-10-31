plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ch.ethan.antiscroll"
    compileSdk = 34
    defaultConfig {
        applicationId = "ch.ethan.antiscroll"
        minSdk = 26
        targetSdk = 34
        // Monte à chaque build GitHub : Android voit une mise à jour
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "1.0." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
    }
    // Clé de signature fixe (fournie par le secret GitHub ANDROID_KEYSTORE_B64) :
    // même clé à chaque build = réinstaller l'APK met à jour l'app au lieu d'être refusé.
    val ks = System.getenv("ANDROID_KEYSTORE_PATH")
    signingConfigs {
        if (ks != null && file(ks).exists()) {
            create("fixe") {
                storeFile = file(ks)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "antiscroll"
                keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        debug { signingConfigs.findByName("fixe")?.let { signingConfig = it } }
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
