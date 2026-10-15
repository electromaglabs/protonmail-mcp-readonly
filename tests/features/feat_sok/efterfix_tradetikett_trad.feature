Feature: get_thread har tak och blockerar inte andra verktyg
  Som användare av MCP-servern
  vill jag att "visa konversationen" alltid blir klar inom rimlig tid
  så att ett mejl med en enorm References-header inte låser alla andra verktyg.

  Varje SEARCH i All Mail tar 3–8 s hos Bridge. References styrs av avsändaren
  och kan innehålla tusentals påhittade ID:n.

  Background:
    Given en brevlåda "All Mail" med mejlen
      | uid  | from             | subject        | date                            | message_id | in_reply_to | references  |
      | 1001 | anna@example.com | Offert         | Mon, 05 Oct 2026 09:00:00 +0200 | <a@x>      |             |             |
      | 1002 | m@neomeda.se     | Re: Offert     | Mon, 05 Oct 2026 10:00:00 +0200 | <b@x>      | <a@x>       | <a@x>       |

  Scenario: Ett mejl med tusentals påhittade ID:n i References ger ett begränsat antal sökningar
    Given ett mejl i INBOX och All Mail med UID "9" som svarar på "<b@x>" och har 5000 påhittade ID:n i References
    When jag hämtar konversationen för UID "9" i INBOX
    Then ska Bridge ha fått högst 10 sökningar
    And ska konversationen inte vara komplett
    And ska anteckningen nämna "söktes inte"

  Scenario: Det närmaste föräldramejlet hittas trots skräp i References
    Given ett mejl i INBOX och All Mail med UID "9" som svarar på "<b@x>" och har 5000 påhittade ID:n i References
    When jag hämtar konversationen för UID "9" i INBOX
    Then ska konversationen innehålla All Mail-UID "1002"

  Scenario: Sökningen stannar när tidsbudgeten är slut
    Given ett mejl i INBOX och All Mail med UID "9" som svarar på "<b@x>" och har 5000 påhittade ID:n i References
    And att varje sökning i All Mail tar 25 sekunder
    When jag hämtar konversationen för UID "9" i INBOX
    Then ska Bridge ha fått högst 3 sökningar
    And ska konversationen inte vara komplett
    And ska anteckningen nämna "tidsgränsen"

  Scenario: Andra verktygsanrop får köra mellan sökningarna
    Given ett mejl i INBOX och All Mail med UID "9" som svarar på "<b@x>" och har 5000 påhittade ID:n i References
    When jag hämtar konversationen för UID "9" i INBOX medan ett annat verktygsanrop väntar på anslutningen
    Then ska det andra anropet ha körts före konversationens andra sökning

  Scenario: En vanlig konversation är fortfarande komplett
    Given en brevlåda INBOX där UID "7" är mejlet med Message-ID "<b@x>"
    When jag hämtar konversationen för UID "7" i INBOX
    Then ska konversationen bestå av All Mail-UID "1001, 1002" i datumordning
    And ska konversationen vara komplett

  Scenario: Ett startmejl utan Message-ID returneras med den mapp där dess UID gäller
    Given en brevlåda "INBOX" med mejlen
      | uid | from             | subject | date                            | message_id |
      | 70  | anna@example.com | Utan ID | Mon, 05 Oct 2026 09:00:00 +0200 |            |
    When jag hämtar konversationen för UID "70" i INBOX
    Then ska konversationen bestå av UID "70"
    And ska varje mejl ha mailbox "INBOX"
    And ska konversationen inte vara komplett
    And ska anteckningen nämna "mailbox="INBOX""

  Scenario: Verktygsbeskrivningen säger att varje mejl läses i sitt eget mailbox-fält
    Then ska beskrivningen av get_thread hänvisa till varje mejls mailbox-fält
