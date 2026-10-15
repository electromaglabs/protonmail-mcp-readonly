Feature: Begripliga och handlingsbara felmeddelanden
  Som modell som använder verktygen
  vill jag få fel på svenska som säger vad som gick fel och vad jag kan göra
  i stället för interna undantag och stackspår.

  Scenario: Ett ogiltigt värde ger felets egen text
    Given att Bridge avvisar anropet med felet "Ogiltigt UID: 'abc'"
    When jag anropar list_mailboxes
    Then ska anropet misslyckas med texten "Ogiltigt UID: 'abc'"
    And ska felet inte innehålla något stackspår

  Scenario Outline: Bridge går inte att nå
    Given att anslutningen till Bridge misslyckas med <fel>
    When jag anropar list_mailboxes
    Then ska anropet misslyckas med texten "Kan inte nå ProtonMail Bridge"
    And ska felet fråga om Bridge körs
    And ska felet inte innehålla något stackspår

    Examples:
      | fel                  |
      | anslutning nekad     |
      | timeout              |
      | avbruten anslutning  |
      | aioimaplib-protokoll |

  Scenario: Fel användarnamn eller Bridge-lösenord vid läsning
    Given att Bridge nekar inloggningen över IMAP
    When jag anropar list_mailboxes
    Then ska anropet misslyckas med texten "PROTONMAIL_USERNAME"
    And ska felet nämna Bridge-lösenordet

  Scenario: Fel användarnamn eller Bridge-lösenord vid skick
    Given att Bridge nekar inloggningen över SMTP
    When jag skickar ett mejl till "anna@example.com"
    Then ska anropet misslyckas med texten "PROTONMAIL_USERNAME"
    And ska felet nämna Bridge-lösenordet

  Scenario: Servern vägrar några av mottagarna
    Given att servern levererar till "anna@example.com" men vägrar "okand@example.com"
    When jag skickar ett mejl till "anna@example.com" och "okand@example.com"
    Then ska anropet misslyckas med texten "anna@example.com"
    And ska felet nämna att "okand@example.com" inte fick mejlet
    And ska felet säga att mejlet inte ska skickas om till alla

  Scenario: Anslutningen bryts när ett mejl skickas
    Given att anslutningen bryts när mejlet skickas
    When jag skickar ett mejl till "anna@example.com"
    Then ska anropet misslyckas med texten "Kan inte nå ProtonMail Bridge"
    And ska felet säga att mejlet kan ha skickats och att Sent ska kontrolleras

  Scenario: Ett oväntat internt fel
    Given att ett oväntat internt fel med texten "intern detalj" inträffar
    When jag anropar list_mailboxes
    Then ska anropet misslyckas med texten "Oväntat fel"
    And ska felet inte innehålla texten "intern detalj"
    And ska felet vara loggat till stderr med stackspår
