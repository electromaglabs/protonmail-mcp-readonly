Feature: Fler sökfilter i search_emails
  Som en MCP-klient
  vill jag kunna söka på mottagare, kopia, brödtext, stjärna, besvarad och storlek
  för att hitta rätt mejl utan att läsa igenom hela mappen.

  Bridge jämför sökord mot det okodade meddelandet: headers med åäö är
  RFC 2047-kodade och brödtexten är quoted-printable. Filtren ska ändå
  hitta det användaren menar.

  Background:
    Given en brevlåda INBOX med mejlen
      | uid | from              | to                      | cc               | subject       | body                        | flags     | size    |
      | 101 | anna@example.com  | Mattias <m@neomeda.se>  |                  | Lunch         | Ses vi på fredag?           |           | 2000    |
      | 102 | bo@example.com    | =?utf-8?q?G=C3=B6ran?= <goran@example.com> | m@neomeda.se | Offert        | Vi behöver offerten i dag   | Flagged   | 9000000 |
      | 103 | cilla@example.com | m@neomeda.se            | anna@example.com | Re: Lunch     | Fredag passar bra           | Answered  | 3000    |

  Scenario: Söka på mottagare med åäö i visningsnamnet
    When jag söker i INBOX med to_addr "Göran"
    Then ska träffarna vara UID "102"

  Scenario: Söka på kopiemottagare
    When jag söker i INBOX med cc_addr "anna@example.com"
    Then ska träffarna vara UID "103"

  Scenario: Söka i brödtexten med åäö trots quoted-printable
    When jag söker i INBOX med body "behöver"
    Then ska träffarna vara UID "102"

  Scenario: Söka i hela meddelandet
    When jag söker i INBOX med text "fredag"
    Then ska träffarna vara UID "103, 101"

  Scenario: Bara stjärnmärkta mejl
    When jag söker i INBOX med flagged true
    Then ska träffarna vara UID "102"

  Scenario: Bara obesvarade mejl
    When jag söker i INBOX med answered false
    Then ska träffarna vara UID "102, 101"

  Scenario: Bara stora mejl
    When jag söker i INBOX med larger_than 1000000
    Then ska träffarna vara UID "102"

  Scenario: Bara små mejl
    When jag söker i INBOX med smaller_than 2500
    Then ska träffarna vara UID "101"

  Scenario: Kontrolltecken i ett sökvärde avvisas innan Bridge får något
    When jag söker i INBOX med en text som innehåller en radbrytning följd av ett IMAP-kommando
    Then ska sökningen avvisas med "kontrolltecken"
    And ska inget sökkommando ha skickats till Bridge
