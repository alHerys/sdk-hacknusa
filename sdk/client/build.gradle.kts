plugins { kotlin("jvm") }
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11) } }
dependencies {
    api(project(":qrishield-core"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    testImplementation("junit:junit:4.13.2")
}

java { sourceCompatibility = JavaVersion.VERSION_11; targetCompatibility = JavaVersion.VERSION_11 }

// Explicit real-service acceptance; default unit tests do not need a running model.
tasks.test { exclude("**/LocalHttpTest*") }
tasks.register<Test>("localHttpSmoke") {
    description = "Verify Kotlin client over actual authenticated loopback HTTP"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    filter { includeTestsMatching("com.hacknusa.qrishield.client.LocalHttpTest") }
    systemProperty("qrishield.serviceDir", rootProject.file("services/laya").absolutePath)
}
