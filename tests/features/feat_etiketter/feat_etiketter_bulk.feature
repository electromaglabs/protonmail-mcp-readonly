Feature: Hantera flera mejl i ett anrop
  Som en MCP-klient
  vill jag kunna markera, flytta, radera och etikettera upp till 100 mejl i ett anrop
  och få veta för varje mejl om det lyckades.

  Scenario: Flera mejl markeras som lästa med ett enda kommando
    Given att mejlen med UID "1, 5, 9" ligger i "INBOX"
    When jag markerar UID-listan "1, 5, 9" i "INBOX" som lästa
    Then ska resultatet ha ok "1, 5, 9" och inga misslyckade
    And ska Bridge ha fått "UID STORE" med "1,5,9 +FLAGS (\Seen)"

  Scenario: Ett UID som saknas rapporteras utan att stoppa de andra
    Given att mejlen med UID "1, 5" ligger i "INBOX"
    When jag markerar UID-listan "1, 5, 9" i "INBOX" som lästa
    Then ska resultatet ha ok "1, 5" och UID "9" misslyckat med "Inget meddelande med UID 9 i INBOX"
    And ska Bridge ha fått "UID STORE" med "1,5 +FLAGS (\Seen)"

  Scenario: Flera mejl flyttas med UID MOVE i ett kommando
    Given att mejlen med UID "1, 5" ligger i "INBOX"
    When jag flyttar UID-listan "1, 5" från "INBOX" till "Archive"
    Then ska resultatet ha ok "1, 5" och inga misslyckade
    And ska Bridge ha fått "UID MOVE" med "1,5 "Archive""
    And ska Bridge inte ha fått "EXPUNGE"

  Scenario: Säkerhetsvakterna gäller också för listor
    Given att mejlen med UID "1, 5" ligger i "Starred"
    When jag flyttar UID-listan "1, 5" från "Starred" till "Trash"
    Then ska verktyget ge ett fel som nämner "redan ligga i Trash"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Flera mejl tas bort till papperskorgen
    Given att mejlen med UID "1, 5" ligger i "INBOX"
    When jag tar bort UID-listan "1, 5" i "INBOX"
    Then ska resultatet ha ok "1, 5" och inga misslyckade
    And ska Bridge ha fått "UID MOVE" med "1,5 "Trash""

  Scenario: Permanent radering av flera mejl rör bara de angivna UID:na
    Given att mejlen med UID "1, 5, 6" ligger i "Trash"
    When jag raderar UID-listan "1, 5" i "Trash" permanent
    Then ska resultatet ha ok "1, 5" och inga misslyckade
    And ska Bridge ha fått "UID STORE" med "1,5 +FLAGS (\Deleted)"
    And ska Bridge ha fått "UID EXPUNGE" med "1,5"
    And ska Bridge inte ha fått "EXPUNGE"

  Scenario: Flera mejl får en etikett i ett kommando
    Given att etiketten "Labels/Kvitton" finns
    And att mejlen med UID "1, 5" ligger i "INBOX"
    When jag lägger till etiketten "Kvitton" på UID-listan "1, 5" i "INBOX"
    Then ska resultatet ha ok "1, 5" och inga misslyckade
    And ska Bridge ha fått "UID COPY" med "1,5 "Labels/Kvitton""

  Scenario: Etiketten tas bort från flera mejl och den som saknar etiketten rapporteras
    Given att etiketten "Labels/Kvitton" finns
    And att mejlet med UID "1" och Message-ID "<a@x>" ligger i "INBOX"
    And att mejlet med Message-ID "<a@x>" har etiketten "Labels/Kvitton" med UID "11"
    And att mejlet med UID "5" och Message-ID "<b@x>" ligger i "INBOX"
    When jag tar bort etiketten "Kvitton" från UID-listan "1, 5" i "INBOX"
    Then ska resultatet ha ok "1" och UID "5" misslyckat med "har inte etiketten Labels/Kvitton"
    And ska Bridge ha fått "UID EXPUNGE" med "11"

  Scenario: Flera mejl stjärnmärks
    Given att mejlen med UID "1, 5" ligger i "INBOX"
    When jag stjärnmärker UID-listan "1, 5" i "INBOX"
    Then ska resultatet ha ok "1, 5" och inga misslyckade
    And ska Bridge ha fått "UID STORE" med "1,5 +FLAGS (\Flagged)"

  Scenario: Fler än 100 UID:n avvisas innan Bridge kontaktas
    When jag markerar 101 UID:n i "INBOX" som lästa
    Then ska verktyget ge ett fel som nämner "högst 100"
    And ska Bridge inte ha fått något kommando

  Scenario: Ett ogiltigt UID i listan avvisar hela anropet innan Bridge kontaktas
    When jag markerar UID-listan "1, 5:9" i "INBOX" som lästa
    Then ska verktyget ge ett fel som nämner "Ogiltigt UID"
    And ska Bridge inte ha fått något kommando
