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

  Scenario: Mejl enbart till hemlig kopia får ingen tom To-header
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail utan mottagare men med hemlig kopia till "hemlig@example.se"
    Then ska mejlet sakna headern "To"
    And ska mejlet sakna headern "Bcc"
    And SMTP-mottagarna ska vara "hemlig@example.se"

  Scenario: Message-ID avslöjar inte datorns värdnamn
    Given en SMTP-klient för kontot "anna@proton.me"
    When jag skickar ett mail till "bob@example.com"
    Then ska Message-ID sluta med "@proton.me>"
