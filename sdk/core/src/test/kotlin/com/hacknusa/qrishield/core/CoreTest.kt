package com.hacknusa.qrishield.core
import org.junit.Test
import org.junit.Assert.*
class CoreTest {
    private val valid = "00020101021251280014ID.CO.QRIS.WWW0206TEST0152045812530336054063500005802ID5913TEST MERCHANT6007JAKARTA63046D26"
    private fun sign(s: String) = s.dropLast(4) + "%04X".format(QrisParser.crc16(s.dropLast(4)))
    @Test fun parserStatusesAndExactMoney() {
        assertEquals(0x29b1, QrisParser.crc16("123456789"))
        assertEquals(350000L, QrisParser.parse(valid).transaction.amountMinor)
        assertEquals(ParseStatus.SUCCESS, QrisParser.parse(valid).parseStatus)
        assertEquals(ParseStatus.NOT_QRIS, QrisParser.parse("https://example.test").parseStatus)
        assertEquals(ParseStatus.MALFORMED, QrisParser.parse(valid.replace("5802ID", "5802ID5802ID")).parseStatus)
        assertEquals(ParseStatus.INVALID_CRC, QrisParser.parse(valid.dropLast(4)+"0000").parseStatus)
        assertEquals(ParseStatus.UNSUPPORTED, QrisParser.parse(valid.replace("TEST", "TÉST")).parseStatus)
        assertEquals(ParseStatus.UNSUPPORTED_AMOUNT, QrisParser.parse(sign(valid.replace("5406350000", "5408350000.5"))).parseStatus)
        assertNull(QrisParser.parse(sign(valid.replace("5406350000", ""))).transaction.amountMinor)
        assertNull(QrisParser.parse(valid.dropLast(4)+"0000").usableMerchant())
    }
    @Test fun merchantChannelAndNestedDuplicateRejection() {
        fun channel(c: String) = sign(valid.replace("6304", "62" + (4+c.length).toString().padStart(2,'0') + "11" + c.length.toString().padStart(2,'0') + c + "6304"))
        for (m in 0..7) for (l in 0..3) for (p in 0..3) assertEquals(ParseStatus.SUCCESS, QrisParser.parse(channel("$m$l$p")).parseStatus)
        assertEquals(ParseStatus.UNSUPPORTED, QrisParser.parse(channel("800")).parseStatus)
        assertEquals(ParseStatus.MALFORMED, QrisParser.parse(channel("00")).parseStatus)
        assertEquals(ParseStatus.MALFORMED, QrisParser.parse(sign(valid.replace("6304", "6214110300011030006304"))).parseStatus)
    }
    @Test fun textUsesUtf16AndNoHiddenTruncation() {
        assertEquals(TextCondition.OBSERVED, textCondition("😀".repeat(2048)))
        assertEquals(TextCondition.OVERSIZED, textCondition("😀".repeat(2049)))
        assertEquals(TextCondition.INVALID_UNICODE, textCondition("\uD800"))
        assertEquals(TextCondition.ABSENT, textCondition("  "))
        val text = "x".repeat(5000); assertEquals(text, ReviewedContext(text, text).text)
        assertFalse(ReviewedContext(text, text).toString().contains(text))
    }
    @Test fun snapshotsCopyCandidateCollectionsAndDoNotInventLinkage() {
        val list = mutableListOf(ContextCandidate("one", "bayar"))
        val frozen = ContextMatchRequest(QrObservation(valid), list, ProcessingPermissions(matching=true), 30000).frozen()
        list.clear(); assertEquals(1, frozen.candidates.size)
        assertNull(frozen.candidates[0].provenance.sameConversation)
        assertNull(frozen.candidates[0].provenance.messageMediaDeltaMs)
    }
}
