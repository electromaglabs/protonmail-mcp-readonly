Feature: Vattenmärket för nya mejl går inte att förgifta
  Som användare
  vill jag att inget anrop kan få servern att hoppa över riktiga nya mejl
  så att ett mejl aldrig försvinner ur "nya mejl" för att någon angav ett konstigt UID.

  Vattenmärket flyttas bara framåt, bara till det högsta UID som faktiskt
  visats, och aldrig förbi det senaste mejlet i mappen. since_uid är en
  engångsfråga och ändrar det inte.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3

  Scenario Outline: Ett påhittat högt since_uid får inte dölja nästa mejl
    Given att <bevakning>
    And att jag har anropat check_new_emails för INBOX
    When jag anropar check_new_emails för INBOX med since_uid "999999999"
    Then ska svaret inte innehålla några mejl
    When ett mejl med ämnet "Offert" kommer till INBOX
    And jag väntar på nya mejl i INBOX i högst 5 sekunder
    Then ska svaret innehålla UID:n "4" med mailbox "INBOX"

    Examples:
      | bevakning               |
      | servern bevakar INBOX   |
      | bevakningen är avstängd |

  Scenario: since_uid ändrar inte vattenmärket bakåt eller framåt
    Given att servern bevakar INBOX
    And att jag har anropat check_new_emails för INBOX
    When jag anropar check_new_emails för INBOX med since_uid "1"
    Then ska svaret innehålla UID:n "3,2" med mailbox "INBOX"
    When jag anropar check_new_emails för INBOX
    Then ska svaret inte innehålla några mejl

  Scenario: En annan mapp påverkar inte INBOX vattenmärke
    Given att servern bevakar INBOX
    And att jag har anropat check_new_emails för INBOX
    When ett mejl med ämnet "Offert" kommer till INBOX
    And jag anropar check_new_emails för "Folders/Kunder" med since_uid "999999999"
    And jag väntar på nya mejl i INBOX i högst 5 sekunder
    Then ska svaret innehålla UID:n "4" med mailbox "INBOX"

  Scenario: wait_for_new_email som går ut flyttar inte vattenmärket
    Given att bevakningen är avstängd
    And att jag har anropat check_new_emails för INBOX
    When jag väntar på nya mejl i INBOX i högst 1 sekunder
    Then ska vattenmärket för INBOX vara UID 3
