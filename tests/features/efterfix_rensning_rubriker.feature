Feature: get_email_headers rensar och märker rubrikerna
  Som användare av en LLM som läser min e-post
  vill jag att även det snabba rubrikverktyget rensar osynliga tecken och märker innehållet som opålitligt
  så att en avsändare inte kan nå modellen med dolda instruktioner via rubrikerna.

  Scenario: Taggtecken i ett ämne med rå UTF-8 tas bort och flaggas
    Given ett mejl vars rubriker är "Subject: hej <taggar>"
    When jag hämtar rubrikerna med get_email_headers
    Then ska rubriken subject vara "hej"
    And ska inget fält i svaret innehålla osynliga tecken
    And ska sanitized räkna subject
    And ska suspicious_content nämna taggtecken
    And ska svaret ha untrusted_content_notice

  Scenario: Ett RFC 2047-ord utan dolda tecken står kvar okodat
    Given ett mejl vars rubriker är "Subject: =?UTF-8?B?w4RyZW5kZQ==?="
    When jag hämtar rubrikerna med get_email_headers
    Then ska rubriken subject vara "=?UTF-8?B?w4RyZW5kZQ==?="
    And ska suspicious_content vara tom

  Scenario: Ett RFC 2047-ord som avkodat har dolda tecken visas avkodat och rensat
    Given ett mejl vars rubriker är "Subject: =?utf-8?b?<base64 för 'Hej' och taggtecken>?="
    When jag hämtar rubrikerna med get_email_headers
    Then ska rubriken subject vara "Hej"
    And ska inget fält i svaret innehålla osynliga tecken
    And ska suspicious_content nämna taggtecken

  Scenario: Message-ID med taggtecken visas bara som ASCII-msg-id
    Given ett mejl vars rubriker är "Message-ID: <a<taggar>@x> <ok@x>"
    When jag hämtar rubrikerna med get_email_headers
    Then ska rubriken message_id vara "<ok@x>"
    And ska inget fält i svaret innehålla osynliga tecken

  Scenario: Bidi i ett visningsnamn tas bort men osynliga tecken i adressen synliggörs
    Given ett mejl vars rubriker är "From: Anna<rlo> <an<zw>na@x.se>"
    When jag hämtar rubrikerna med get_email_headers
    Then ska rubriken from vara "Anna <an[U+200B]na@x.se>"
    And ska inget fält i svaret innehålla osynliga tecken
    And ska suspicious_content nämna osynliga tecken i en adress
