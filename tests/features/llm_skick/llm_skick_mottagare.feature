Feature: Tillåtna mottagare (PROTONMAIL_ALLOWED_RECIPIENTS)
  Som användare som låter en LLM skicka e-post åt mig
  vill jag kunna begränsa vilka adresser och domäner den får skicka till
  så att en promptinjektion inte kan skicka mina mejl till en främling.

  Scenario: Mejl till en tillåten domän skickas
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@exempel.se, chef@firma.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se" med kopia till "chef@firma.se"
    Then ska mejlet ha skickats till "anna@exempel.se, chef@firma.se"

  Scenario: En enda otillåten mottagare stoppar hela skicket
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@exempel.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se" med kopia till "eva@annat.se"
    Then ska anropet vägras med ett fel som nämner "eva@annat.se"
    And ska felet inte nämna "anna@exempel.se" som otillåten
    And ska Bridge inte ha kontaktats

  Scenario: Hemlig kopia kontrolleras också
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@exempel.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@exempel.se" med hemlig kopia till "spion@ond.example"
    Then ska anropet vägras med ett fel som nämner "spion@ond.example"
    And ska Bridge inte ha kontaktats

  Scenario: Domänen jämförs utan hänsyn till skiftläge
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@Exempel.SE"
    When koden direkt i SMTP-klienten skickar ett mejl till "anna@EXEMPEL.se"
    Then ska mejlet ha skickats till "anna@EXEMPEL.se"

  Scenario: En adress i listan tillåter bara exakt den adressen
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "bo@exempel.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "bob@exempel.se" med kopia till "bo@exempel.se.ond.example"
    Then ska anropet vägras med ett fel som nämner "bob@exempel.se"
    And ska felet nämna "bo@exempel.se.ond.example"

  Scenario: Internationaliserade domännamn jämförs i punycode
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@exämple.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "user@xn--exmple-cua.se" med kopia till "van@EXÄMPLE.se"
    Then ska mejlet ha skickats till "user@xn--exmple-cua.se, van@xn--exmple-cua.se"

  Scenario: Utkast som skickas med send_draft kontrolleras
    Given servern körs med inställningen "allowed_recipients" satt till "@exempel.se"
    And Drafts har utkastet med UID "7" till "anna@exempel.se" och hemlig kopia till "spion@ond.example"
    When LLM:en anropar verktyget "send_draft"
    Then ska anropet vägras med ett fel som nämner "spion@ond.example"
    And ska inget mejl ha skickats

  Scenario: Vidarebefordran kontrolleras
    Given servern körs med inställningen "allowed_recipients" satt till "@exempel.se"
    And INBOX har ett mejl med UID "5" från "kund@exempel.se"
    When LLM:en vidarebefordrar UID "5" i "INBOX" till "extern@annat.se"
    Then ska anropet vägras med ett fel som nämner "extern@annat.se"
    And ska inget mejl ha skickats

  Scenario: En felskriven post i listan stoppar servern vid start
    When inställningen "allowed_recipients" läses som "@exempel.se, inte en adress"
    Then ska inställningen underkännas med ett fel som nämner "inte en adress"
