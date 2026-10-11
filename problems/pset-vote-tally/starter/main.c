#include <stdio.h>

#define MAX_CANDIDATE 1000

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;

    int counts[MAX_CANDIDATE + 1] = {0};

    // TODO: read each of the n ballots and increment counts[ballot].
    for (int i = 0; i < n; i++) {
        int ballot;
        if (scanf("%d", &ballot) != 1) return 0;
        (void)ballot;
    }

    // TODO: find the candidate with the most votes, breaking ties toward the
    // smallest candidate number, and track the best count.

    // TODO: decide whether the winner has a strict majority (more than n/2)
    // and print "<candidate> majority" or "<candidate> plurality".
    printf("1 plurality\n");
    return 0;
}
