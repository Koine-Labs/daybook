import XCTest
@testable import Lullaby

/// Tests for ConnectivityMessageType, ConnectivityEnvelope, and SessionControlCommand.
final class ConnectivityMessageTests: XCTestCase {

    // MARK: - ConnectivityMessageType

    func testMessageTypeRawValues() {
        XCTAssertEqual(ConnectivityMessageType.sensorPacket.rawValue, "sensorPacket")
        XCTAssertEqual(ConnectivityMessageType.sessionControl.rawValue, "sessionControl")
    }

    // MARK: - ConnectivityEnvelope Codable

    func testEnvelopeCodableRoundtrip() throws {
        let envelope = ConnectivityEnvelope(
            type: .sensorPacket,
            payload: Data("test-payload".utf8),
            sequenceNumber: 42,
            sentAt: Date(timeIntervalSinceReferenceDate: 700_000_000)
        )
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        let data = try encoder.encode(envelope)
        let decoded = try decoder.decode(ConnectivityEnvelope.self, from: data)

        XCTAssertEqual(decoded.type, envelope.type)
        XCTAssertEqual(decoded.payload, envelope.payload)
        XCTAssertEqual(decoded.sequenceNumber, envelope.sequenceNumber)
    }

    // MARK: - toDictionary

    func testToDictionaryContainsExpectedKeys() {
        let envelope = ConnectivityEnvelope(
            type: .sessionControl,
            payload: Data("cmd".utf8),
            sequenceNumber: 1,
            sentAt: Date(timeIntervalSinceReferenceDate: 700_000_000)
        )
        let dict = envelope.toDictionary()
        XCTAssertNotNil(dict["type"] as? String)
        XCTAssertNotNil(dict["payload"] as? Data)
        XCTAssertNotNil(dict["seq"] as? UInt64)
        XCTAssertNotNil(dict["sentAt"] as? TimeInterval)
    }

    func testToDictionaryTypeValue() {
        let envelope = ConnectivityEnvelope(
            type: .sensorPacket,
            payload: Data(),
            sequenceNumber: 0,
            sentAt: Date()
        )
        let dict = envelope.toDictionary()
        XCTAssertEqual(dict["type"] as? String, "sensorPacket")
    }

    // MARK: - from(dictionary:)

    func testFromDictionaryValid() {
        let date = Date(timeIntervalSinceReferenceDate: 700_000_000)
        let dict: [String: Any] = [
            "type": "sensorPacket",
            "payload": Data("hello".utf8),
            "seq": UInt64(5),
            "sentAt": date.timeIntervalSinceReferenceDate
        ]
        let envelope = ConnectivityEnvelope.from(dictionary: dict)
        XCTAssertNotNil(envelope)
        XCTAssertEqual(envelope?.type, .sensorPacket)
        XCTAssertEqual(envelope?.sequenceNumber, 5)
        XCTAssertEqual(envelope?.payload, Data("hello".utf8))
    }

    func testFromDictionaryMissingKeyReturnsNil() {
        let dict: [String: Any] = [
            "type": "sensorPacket",
            "payload": Data(),
            // missing "seq" and "sentAt"
        ]
        let envelope = ConnectivityEnvelope.from(dictionary: dict)
        XCTAssertNil(envelope)
    }

    func testFromDictionaryWrongTypeReturnsNil() {
        let dict: [String: Any] = [
            "type": "invalidType",
            "payload": Data(),
            "seq": UInt64(0),
            "sentAt": Date().timeIntervalSinceReferenceDate
        ]
        let envelope = ConnectivityEnvelope.from(dictionary: dict)
        XCTAssertNil(envelope)
    }

    func testFromDictionaryWrongPayloadTypeReturnsNil() {
        let dict: [String: Any] = [
            "type": "sensorPacket",
            "payload": "not-data",  // String instead of Data
            "seq": UInt64(0),
            "sentAt": Date().timeIntervalSinceReferenceDate
        ]
        let envelope = ConnectivityEnvelope.from(dictionary: dict)
        XCTAssertNil(envelope)
    }

    // MARK: - Roundtrip: toDictionary → from(dictionary:)

    func testDictionaryRoundtrip() {
        let original = ConnectivityEnvelope(
            type: .sessionControl,
            payload: Data("roundtrip".utf8),
            sequenceNumber: 99,
            sentAt: Date(timeIntervalSinceReferenceDate: 750_000_000)
        )
        let dict = original.toDictionary()
        let reconstructed = ConnectivityEnvelope.from(dictionary: dict)

        XCTAssertNotNil(reconstructed)
        XCTAssertEqual(reconstructed?.type, original.type)
        XCTAssertEqual(reconstructed?.payload, original.payload)
        XCTAssertEqual(reconstructed?.sequenceNumber, original.sequenceNumber)
    }

    // MARK: - SessionControlCommand

    func testSessionControlCommandAllCases() throws {
        let encoder = JSONEncoder()
        let decoder = JSONDecoder()

        let allCases: [SessionControlCommand] = [.sessionStarted, .sessionStopped, .phoneReady]
        for cmd in allCases {
            let data = try encoder.encode(cmd)
            let decoded = try decoder.decode(SessionControlCommand.self, from: data)
            XCTAssertEqual(cmd, decoded, "Roundtrip failed for \(cmd)")
        }
    }

    func testSessionControlCommandRawValues() {
        XCTAssertEqual(SessionControlCommand.sessionStarted.rawValue, "sessionStarted")
        XCTAssertEqual(SessionControlCommand.sessionStopped.rawValue, "sessionStopped")
        XCTAssertEqual(SessionControlCommand.phoneReady.rawValue, "phoneReady")
    }
}
