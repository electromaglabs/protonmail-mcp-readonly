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

  Scenario: Ett ämne längre än 998 tecken kan skickas och viks på flera rader
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "bob@example.com" med ett ämne på 1002 tecken
    Then ska mejlet ha skickats
    And ska ämnet vara oförändrat efter överföringen
    And ska ingen headerrad vara längre än 998 tecken

  Scenario: Ett orimligt långt ämne avvisas
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "bob@example.com" med ett ämne på 10001 tecken
    Then ska sändningen avvisas med ett fel som nämner "för lång"
    And inget mejl ska ha skickats

  Scenario: Ämne med radbrytning avvisas fortfarande
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "bob@example.com" med ämnet "Hej\nBcc: evil@example.com"
    Then ska sändningen avvisas med ett fel som nämner "radbrytningar"
    And inget mejl ska ha skickats

  Scenario: Servern vägrar en av flera mottagare
    Given en SMTP-klient för kontot "me@proton.me"
    And att servern vägrar mottagaren "fel@example.se" med 550 "No such user"
    When jag skickar ett mail till "ok@example.se" och "fel@example.se"
    Then ska felet nämna "fel@example.se"
    And ska felet nämna "550 No such user"
    And ska felet tala om att mejlet gick fram till "ok@example.se"

  Scenario: Servern godtar alla mottagare
    Given en SMTP-klient för kontot "me@proton.me"
    When jag skickar ett mail till "ok@example.se" och "ok2@example.se"
    Then ska mejlet ha skickats
