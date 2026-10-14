Feature: Långa blankteckenföljder i rubriker låser inte servern
  Som användare av MCP-servern
  vill jag att ett mejl med en extremt lång rubrik inte kan låsa servern,
  eftersom alla andra anrop väntar medan rubrikerna tolkas.

  Scenario: Ett ämne med 30 000 blanksteg mitt i tolkas snabbt
    Given att mejlet med UID "7" i "INBOX" har ett ämne med 30000 blanksteg mitt i
    When jag hämtar rubrikerna för UID "7" i "INBOX"
    Then ska svaret komma inom 1 sekund
