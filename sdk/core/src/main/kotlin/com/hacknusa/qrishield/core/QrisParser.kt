package com.hacknusa.qrishield.core

import java.math.BigDecimal

/** Supported ASCII EMV MPM core; not scheme certification or merchant authentication. */
enum class ParseStatus { SUCCESS, NOT_QRIS, MALFORMED, INVALID_CRC, UNSUPPORTED, UNSUPPORTED_AMOUNT }
data class Merchant(
    val name: String?, val merchantId: String? = null,
    val city: String? = null, val postalCode: String? = null, val country: String? = null,
    val merchantPan: String? = null, val acquirerId: String? = null, val acquirerName: String? = null
)
data class Transaction(val amountMinor: Long?, val currency: String?, val amountEncoded: Boolean?, val dynamic: Boolean?)
data class Integrity(val crcValid: Boolean?, val emvValid: Boolean?)
data class ParsedQris(val parseStatus: ParseStatus, val merchant: Merchant, val transaction: Transaction, val integrity: Integrity)

object QrisParser {
    private val digits = Regex("[0-9]+")
    private val amount = Regex("[0-9]+(?:\\.[0-9]{0,2})?")
    private class Invalid : Exception()
    private fun validGui(value: String?): Boolean {
        if (value == null || value.length !in 1..32) return false
        if (Regex("[0-9A-Fa-f]{10,32}").matches(value) && value.length % 2 == 0) return true
        val labels = value.split('.')
        return labels.size >= 2 && labels.all { Regex("[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?").matches(it) }
    }
    private fun tlv(input: String): LinkedHashMap<String, String> {
        val fields = linkedMapOf<String, String>()
        var offset = 0
        while (offset < input.length) {
            if (input.length - offset < 4) throw Invalid()
            val id = input.substring(offset, offset + 2)
            val lengthText = input.substring(offset + 2, offset + 4)
            if (!digits.matches(id) || !digits.matches(lengthText)) throw Invalid()
            val length = lengthText.toInt()
            if (length == 0 || offset + 4 + length > input.length || fields.containsKey(id)) throw Invalid()
            fields[id] = input.substring(offset + 4, offset + 4 + length)
            offset += 4 + length
        }
        return fields
    }
    /** CRC16/CCITT-FALSE, UTF-8 bytes, including the CRC tag/length but not its value. */
    fun crc16(input: String): Int {
        var crc = 0xffff
        for (byte in input.toByteArray(Charsets.UTF_8)) {
            crc = crc xor ((byte.toInt() and 255) shl 8)
            repeat(8) { crc = ((crc shl 1) xor if (crc and 0x8000 != 0) 0x1021 else 0) and 0xffff }
        }
        return crc
    }
    fun parse(payload: String): ParsedQris {
        fun failure(status: ParseStatus, crc: Boolean? = null, emv: Boolean? = false) = ParsedQris(
            status, Merchant(null), Transaction(null, null, null, null), Integrity(crc, emv))
        if (payload.length > 4096) return failure(ParseStatus.UNSUPPORTED, emv = null)
        if (!payload.startsWith("000201")) return failure(ParseStatus.NOT_QRIS, emv = null)
        // Root ans fields are ASCII; Unicode language templates need a separate validated profile.
        if (payload.any { it.code !in 32..126 }) return failure(ParseStatus.UNSUPPORTED, emv = null)
        val crc = if (Regex(".*6304[0-9A-F]{4}").matches(payload))
            crc16(payload.dropLast(4)) == payload.takeLast(4).toInt(16) else null
        try {
            val f = tlv(payload)
            if (f.keys.first() != "00" || f["00"] != "01" || f.keys.last() != "63" ||
                f["63"]?.matches(Regex("[0-9A-F]{4}")) != true) throw Invalid()
            if (f["01"] != null && f["01"] !in listOf("11", "12")) throw Invalid()
            if (f["52"]?.matches(Regex("[0-9]{4}")) != true ||
                f["53"]?.matches(Regex("[0-9]{3}")) != true ||
                f["58"]?.matches(Regex("[A-Z]{2}")) != true ||
                f["59"]?.length !in 1..25 || f["59"]!!.isBlank() ||
                f["60"]?.length !in 1..15 || f["60"]!!.isBlank() ||
                (f["61"] != null && (f["61"]!!.length > 10 || f["61"]!!.isBlank()))) throw Invalid()
            val accounts = f.filterKeys { it.toInt() in 2..51 }
            if (accounts.isEmpty()) throw Invalid()
            val templates = accounts.filterKeys { it.toInt() >= 26 }.values.map { tlv(it) }
            if (templates.any { !validGui(it["00"]) }) throw Invalid()
            // Validate known nested objects; network-specific subfields remain opaque.
            val extra = f["62"]?.let { tlv(it) }
            extra?.let { extra ->
                if (extra.any { (id, v) -> id.toInt() in 1..8 && v.length > 25 }) throw Invalid()
                // EMV MPM v1.1 4.8.1.6: three Merchant Channel characteristics.
                extra["11"]?.let { if (!Regex("[0-9]{3}").matches(it)) throw Invalid() }
                extra["09"]?.let { if (it.length !in 1..3 || it.any { c -> c !in "AME" } || it.toSet().size != it.length) throw Invalid() }
                extra.filterKeys { it.toInt() in 50..99 }.values.forEach { if (!validGui(tlv(it)["00"])) throw Invalid() }
            }
            f.filterKeys { it.toInt() in 80..99 }.values.forEach { if (!validGui(tlv(it)["00"])) throw Invalid() }
            val encoded = f.containsKey("54")
            val decimal = f["54"]?.let { if (it.length > 13 || !amount.matches(it)) throw Invalid(); BigDecimal(it).also { a -> if (a.signum() <= 0) throw Invalid() } }
            val tip = f["55"]
            if (tip != null && tip !in listOf("01", "02", "03")) throw Invalid()
            if ((tip == "02") != f.containsKey("56") || (tip == "03") != f.containsKey("57")) throw Invalid()
            f["56"]?.let { if (it.length > 13 || !amount.matches(it) || BigDecimal(it).signum() <= 0) throw Invalid() }
            f["57"]?.let { if (it.length > 5 || !amount.matches(it) || BigDecimal(it) < BigDecimal("0.01") || BigDecimal(it) > BigDecimal("99.99")) throw Invalid() }
            // Deliberately do not certify fields/profile variants we do not validate.
            val unknown = f.keys.any { (it.toInt() in 65..79 || it.toInt() in 6..8 || it.toInt() in 17..25) } || f.containsKey("64") ||
                extra?.let { it.keys.any { id -> id == "00" || id == "10" || id.toInt() in 12..49 } } == true
            val unsupportedChannel = extra?.get("11")?.let { !Regex("[0-7][0-3][0-3]").matches(it) } == true
            if (unknown || unsupportedChannel) return failure(ParseStatus.UNSUPPORTED, crc, null)
            val isQris = f["58"] == "ID" && f["53"] == "360" && templates.any { it["00"] == "ID.CO.QRIS.WWW" }
            if (!isQris) return failure(ParseStatus.NOT_QRIS, crc, true)
            val wholeRupiah = decimal?.let { runCatching { it.longValueExact() }.getOrNull() }
            val status = when {
                crc != true -> ParseStatus.INVALID_CRC
                decimal != null && wholeRupiah == null -> ParseStatus.UNSUPPORTED_AMOUNT
                else -> ParseStatus.SUCCESS
            }
            return ParsedQris(status, Merchant(f["59"], city = f["60"].takeIf { crc == true },
                postalCode = f["61"].takeIf { crc == true }, country = f["58"].takeIf { crc == true }), Transaction(wholeRupiah, "IDR", encoded,
                f["01"]?.let { it == "12" }), Integrity(crc, true))
        } catch (_: Invalid) { return failure(ParseStatus.MALFORMED, crc)
        } catch (_: NumberFormatException) { return failure(ParseStatus.MALFORMED, crc) }
    }
}
