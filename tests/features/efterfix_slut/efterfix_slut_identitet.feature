Feature: Samma Proton-mejl känns igen på Protons eget mejl-id
  Som en MCP-klient
  vill jag att move_email, delete_email och remove_label bara räknar ett mejl som
  "samma mejl" när det verkligen är det (X-Pm-Internal-Id), eftersom två olika mejl
  kan ha samma Message-ID, tid och storlek, och att ett tvetydigt fall blir ett fel
  i stället för ett påstått lyckat resultat.

  Scenario: Ett annat mejl med samma Message-ID, tid och storlek i papperskorgen hindrar inte borttagningen
    Given att mejlet "<a@x>" ligger i "INBOX" med UID "1" och i All Mail med UID "50"
    And att ett annat mejl "tvillingen" med samma Message-ID "<a@x>", tid och storlek ligger i "Trash" med UID "9"
    When jag tar bort UID-listan "1" i "INBOX"
    Then ska verktyget svara att UID "1" lyckades
    And ska mejlet "<a@x>" bara ligga i "Trash, All Mail"
    And ska mejlet "tvillingen" bara ligga i "Trash"

  Scenario: Samma Proton-mejl som redan ligger i papperskorgen lämnas orört
    Given att mejlet "<a@x>" ligger i "Sent" med UID "1" och i All Mail med UID "50"
    And att samma Proton-mejl "<a@x>" också syns i "Trash" med UID "9"
    When jag tar bort mejlet med UID "1" i "Sent"
    Then ska verktyget svara att det lyckades
    And ska svaret ha en förklaring som nämner "ligger redan i papperskorgen"
    And ska Bridge inte ha fått några skrivkommandon

  Scenario: Utan X-Pm-Internal-Id blir flera likadana mejl i målet ett fel, inte ett lyckat svar
    Given att Bridge inte visar X-Pm-Internal-Id
    And att mejlet "<a@x>" ligger i "INBOX" med UID "1" och i All Mail med UID "50"
    And att ett annat mejl "tvilling 1" med samma Message-ID "<a@x>", tid och storlek ligger i "Trash" med UID "9"
    And att ett annat mejl "tvilling 2" med samma Message-ID "<a@x>", tid och storlek ligger i "Trash" med UID "10"
    When jag tar bort UID-listan "1" i "INBOX"
    Then ska inget UID ha lyckats
    And ska verktyget ge ett fel som nämner "går inte att avgöra"
    And ska Bridge inte ha fått några skrivkommandon
    And ska mejlet "<a@x>" bara ligga i "INBOX, All Mail"

  Scenario: Etiketten tas bort från rätt mejl när en tvilling har samma etikett
    Given att mejlet "<a@x>" ligger i "INBOX" med UID "1"
    And att samma Proton-mejl "<a@x>" också syns i "Labels/Kvitton" med UID "3"
    And att ett annat mejl "tvillingen" med samma Message-ID "<a@x>", tid och storlek ligger i "INBOX" med UID "2"
    And att mejlet "tvillingen" också syns i "Labels/Kvitton" med UID "4"
    When jag tar bort etiketten "Kvitton" från UID "1" i "INBOX"
    Then ska verktyget svara att det lyckades
    And ska mejlet "<a@x>" bara ligga i "INBOX"
    And ska mejlet "tvillingen" bara ligga i "INBOX, Labels/Kvitton"
