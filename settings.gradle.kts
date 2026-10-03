pluginManagement {
    repositories { mavenCentral(); gradlePluginPortal(); google() }
    resolutionStrategy { eachPlugin { if (requested.id.id == "org.jetbrains.kotlin.jvm") useModule("org.jetbrains.kotlin:kotlin-gradle-plugin:${requested.version}") } }
}
dependencyResolutionManagement { repositories { mavenCentral(); google() } }
rootProject.name = "qrishield-sdk"
include(":qrishield-core", ":qrishield-client")
project(":qrishield-core").projectDir = file("sdk/core")
project(":qrishield-client").projectDir = file("sdk/client")
