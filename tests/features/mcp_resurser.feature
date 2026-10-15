Feature: Brevlådan som MCP-resurser
  Som MCP-klient (t.ex. Claude Desktop)
  vill jag kunna läsa mapplistan, en mapps status och enskilda mejl som resurser
  så att användaren kan bifoga dem till samtalet utan att modellen behöver anropa verktyg,
  med samma validering, sanering och felmeddelanden som verktygen och utan att något ändras.

  Mappnamnet i URI:n procentkodas (RFC 3986, som uriTemplate-uttrycket {mailbox}
  enligt RFC 6570): allt utom A–Z a–z 0–9 - . _ ~ kodas som UTF-8-byte, även "/".

  Scenario: Resurserna och mallarna listas
    When klienten listar resurserna
    Then ska resursen "mailboxes://" finnas
    And ska resursmallen "mailbox://{mailbox}" finnas
    And ska resursmallen "email://{mailbox}/{uid}" finnas

  Scenario: Mapplistan som resurs
    Given att brevlådan har mapparna "INBOX" och "Labels/Näs Samfällighet"
    When klienten läser resursen "mailboxes://"
    Then ska innehållet vara JSON med mappen "Labels/Näs Samfällighet"

  Scenario Outline: En mapp med snedstreck och å, ä, ö i URI:n
    Given att mappen "<mapp>" har 7 mejl varav 2 olästa
    When klienten läser mappresursen för "<mapp>"
    Then ska URI:n vara "<uri>"
    And ska mappen "<mapp>" ha lästs från Bridge
    And ska innehållet visa 7 mejl varav 2 olästa
    And ska innehållet lista de senaste mejlen med mappen "<mapp>"

    Examples:
      | mapp                    | uri                                              |
      | INBOX                   | mailbox://INBOX                                  |
      | Labels/Näs Samfällighet | mailbox://Labels%2FN%C3%A4s%20Samf%C3%A4llighet  |
      | Folders/A/B             | mailbox://Folders%2FA%2FB                        |

  Scenario: Mappresursen visar högst de 20 senaste mejlen
    Given att mappen "INBOX" har 7 mejl varav 2 olästa
    When klienten läser mappresursen för "INBOX"
    Then ska de senaste mejlen ha hämtats med högst 20 per sida

  Scenario: Ett mejl som resurs
    Given att mejlet med UID 42 i "Labels/Näs Samfällighet" finns
    When klienten läser mejlresursen för UID 42 i "Labels/Näs Samfällighet"
    Then ska innehållet vara samma som get_email ger med body_format "text"
    And ska mejlet ha hämtats från mappen "Labels/Näs Samfällighet"
    And ska mejlet inte ha markerats som läst

  Scenario: Mejlresursen markerar aldrig mejlet som läst i Bridge
    Given en IMAP-anslutning där mejlet med UID 42 i "INBOX" finns
    When klienten läser mejlresursen för UID 42 i "INBOX"
    Then ska mejlet ha hämtats med BODY.PEEK
    And ska inga flaggor ha ändrats

  Scenario: Ett mejl som inte finns
    Given att mejlet med UID 42 i "INBOX" inte finns
    When klienten läser mejlresursen för UID 42 i "INBOX"
    Then ska läsningen misslyckas med texten "Inget meddelande med UID 42 i INBOX"

  Scenario: Ett ogiltigt UID i URI:n
    When klienten läser resursen "email://INBOX/abc"
    Then ska läsningen misslyckas med texten "Ogiltigt UID"
    And ska Bridge inte ha anropats

  Scenario: Bridge går inte att nå
    Given att anslutningen till Bridge nekas
    When klienten läser resursen "mailboxes://"
    Then ska läsningen misslyckas med texten "Kan inte nå ProtonMail Bridge"
    And ska felet inte innehålla något stackspår

  Scenario: En mapp som inte finns
    Given att mappen "Folders/Saknas" inte finns
    When klienten läser mappresursen för "Folders/Saknas"
    Then ska läsningen misslyckas med texten "Folders/Saknas"
