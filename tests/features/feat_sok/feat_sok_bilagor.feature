Feature: Söka mejl med eller utan bilagor
  Som en MCP-klient
  vill jag kunna filtrera på om ett mejl har bilagor
  för att hitta avtal, kvitton och andra filer.

  Bridge bygger mejl med bilagor som multipart och märker bilagorna med
  Content-Disposition: attachment. Inbäddade bilder (inline), t.ex. en logga
  i signaturen, är ingen bilaga.

  Background:
    Given en brevlåda INBOX med mejlen
      | uid | from             | subject        | content_type    | parts               |
      | 201 | a@example.com    | Hyresavtal     | multipart/mixed | text, attachment    |
      | 202 | b@example.com    | Nyhetsbrev     | multipart/mixed | text, inline-bild   |
      | 203 | c@example.com    | Hej            | text/html       | text                |

  Scenario: Bara mejl med bilagor
    When jag söker i INBOX med has_attachment true
    Then ska träffarna vara UID "201"

  Scenario: Bara mejl utan bilagor
    When jag söker i INBOX med has_attachment false
    Then ska träffarna vara UID "203, 202"
