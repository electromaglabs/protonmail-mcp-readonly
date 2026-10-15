Feature: Internationella domännamn med ß och ς går till rätt domän (IDNA2008)
  Som användare som mejlar till en tysk eller grekisk domän med ß eller ς
  vill jag att mejlet levereras till exakt den domän jag skrev
  så att det inte tyst hamnar hos en annan organisation (straße.de är inte strasse.de).

  Scenario: Mejl till en domän med ß går till domänens egen punycode
    Given en SMTP-klient för ett konto utan begränsningar
    When koden direkt i SMTP-klienten skickar ett mejl till "info@straße.de"
    Then ska mejlet ha skickats till "info@xn--strae-oqa.de"

  Scenario: Mejl till en grekisk domän med slutsigma går till rätt domän
    Given en SMTP-klient för ett konto utan begränsningar
    When koden direkt i SMTP-klienten skickar ett mejl till "info@σόλος.gr"
    Then ska mejlet ha skickats till "info@xn--wxaijb9b.gr"

  Scenario: En domänpost med ß tillåter just den domänen
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@straße.de"
    When koden direkt i SMTP-klienten skickar ett mejl till "x@straße.de"
    Then ska mejlet ha skickats till "x@xn--strae-oqa.de"

  Scenario: En domänpost med ß tillåter inte domänen med ss
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@straße.de"
    When koden direkt i SMTP-klienten skickar ett mejl till "x@strasse.de"
    Then ska anropet vägras med ett fel som nämner "x@strasse.de"
    And ska Bridge inte ha kontaktats
