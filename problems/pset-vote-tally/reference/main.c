#include <stdio.h>

#define MAX_CANDIDATE 1000

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 0;

    int counts[MAX_CANDIDATE + 1] = {0};

    for (int i = 0; i < n; i++) {
        int ballot;
        if (scanf("%d", &ballot) != 1) return 0;
        counts[ballot]++;
    }

    int best_candidate = 1;
    int best_count = counts[1];
    for (int candidate = 2; candidate <= MAX_CANDIDATE; candidate++) {
        if (counts[candidate] > best_count) {
            best_count = counts[candidate];
            best_candidate = candidate;
        }
    }

    if (best_count * 2 > n) {
        printf("%d majority\n", best_candidate);
    } else {
        printf("%d plurality\n", best_candidate);
    }
    return 0;
}
