Feature: Skicka e-post med korrekta headers
  Som en MCP-klient som skickar e-post till svenska mottagare
  vill jag att adresser, ämne och Message-ID blir rätt kodade
  så att mottagarnas e-postprogram kan läsa och svara på mejlen.

  Scenario: Mottagare med svenska tecken i namnet får en giltig adress
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "Åsa Öberg <asa@example.se>"
    Then ska headern "To" innehålla "Åsa Öberg" med adressen "asa@example.se"
    And SMTP-mottagarna ska vara "asa@example.se"

  Scenario: Kopia och svarsadress med svenska tecken i namnet
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "bob@example.com" med kopia till "Örjan Ås <orjan@example.se>" och svarsadress "Märta Ek <marta@example.se>"
    Then ska headern "Cc" innehålla "Örjan Ås" med adressen "orjan@example.se"
    And ska headern "Reply-To" innehålla "Märta Ek" med adressen "marta@example.se"

  Scenario: Mottagare med internationaliserat domännamn
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "user@exämple.se"
    Then ska headern "To" innehålla "" med adressen "user@xn--exmple-cua.se"
    And SMTP-mottagarna ska vara "user@xn--exmple-cua.se"
