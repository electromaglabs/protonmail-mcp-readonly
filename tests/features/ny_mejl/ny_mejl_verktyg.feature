Feature: Verktyg för nya mejl
  Som modell som hjälper användaren med mejlen
  vill jag kunna fråga efter mejl som kommit sedan sist och vänta på nästa
  så att jag kan reagera på nya mejl utan att lista hela inkorgen om och om igen.

  Verktygen läser bevakningens händelsekö när mappen bevakas. Annars frågar
  de Bridge direkt via den vanliga anslutningen, och säger det i svaret.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3

  Scenario: check_new_emails visar mejl som kommit sedan förra anropet
    Given att servern bevakar INBOX
    When ett mejl med ämnet "Offert" kommer till INBOX och bevakningen har sett det
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla UID:n "4" med mailbox "INBOX"
    And ska svaret säga att INBOX bevakas
    And ska svaret ha tiden för senaste händelsen
    When jag anropar check_new_emails för INBOX
    Then ska svaret inte innehålla några mejl

  Scenario: check_new_emails sedan ett visst UID
    Given att servern bevakar INBOX
    When jag anropar check_new_emails för INBOX med since_uid "1"
    Then ska svaret innehålla UID:n "3,2" med mailbox "INBOX"

  Scenario: Utan bevakning frågas Bridge direkt
    Given att bevakningen är avstängd
    When jag anropar check_new_emails för INBOX
    Then ska svaret inte innehålla några mejl
    And ska anteckningen nämna "Första anropet"
    When ett mejl med ämnet "Offert" kommer till INBOX
    And jag anropar check_new_emails för INBOX
    Then ska svaret innehålla UID:n "4" med mailbox "INBOX"
    And ska svaret säga att INBOX inte bevakas
    And ska anteckningen nämna "avstängd"

  Scenario: check_new_emails markerar inget som läst
    Given att bevakningen är avstängd
    When jag anropar check_new_emails för INBOX med since_uid "0"
    Then ska svaret innehålla UID:n "3,2,1" med mailbox "INBOX"
    And ska Bridge bara ha fått hämtningar med BODY.PEEK
    And ska inget mejl i INBOX vara markerat som läst

  Scenario Outline: wait_for_new_email returnerar när ett mejl kommer
    Given att <bevakning>
    When jag väntar på nya mejl i INBOX i högst 5 sekunder och ett mejl med ämnet "Svar" kommer efter 0.3 sekunder
    Then ska svaret innehålla UID:n "4" med mailbox "INBOX"
    And ska väntan inte ha gått ut
    And ska väntan ha tagit under 2 sekunder

    Examples:
      | bevakning                 |
      | servern bevakar INBOX     |
      | bevakningen är avstängd   |

  Scenario: wait_for_new_email säger till när tiden gått ut
    Given att servern bevakar INBOX
    When jag väntar på nya mejl i INBOX i högst 1 sekunder
    Then ska svaret inte innehålla några mejl
    And ska väntan ha gått ut

  Scenario Outline: Andra verktyg kan köras medan wait_for_new_email väntar
    Given att <bevakning>
    When jag väntar på nya mejl i INBOX i högst 3 sekunder och listar INBOX under tiden
    Then ska listningen ha blivit klar medan väntan pågick

    Examples:
      | bevakning                 |
      | servern bevakar INBOX     |
      | bevakningen är avstängd   |

  Scenario: timeout_seconds utanför 1–300 avvisas
    When jag anropar wait_for_new_email med timeout_seconds 301
    Then ska anropet avvisas utan att Bridge kontaktas
